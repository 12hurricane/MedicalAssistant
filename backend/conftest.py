"""
Shared pytest fixtures.

Every test gets its own throwaway SQLite file. Two reasons:

- ``medication.db`` holds real data used for manual verification. A test that
  writes to it, or rolls it back, destroys that state.
- Per-test isolation means test order cannot matter, so a failure points at the
  test that failed rather than at whatever ran before it.

The schema is built with ``Base.metadata.create_all`` rather than by running the
migrations, for speed. That is only safe because the two are known to agree: the
baseline migration was verified to produce a structurally identical schema, and
``test_migrations.py::test_models_match_migrations`` fails if they ever drift.
"""

import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
import app.models  # noqa: F401  imported for the side effect of registering tables


@pytest.fixture(autouse=True)
def forbid_production_database():
    """
    Make the real database unreachable for the duration of every test.

    This is not hypothetical. ``test_adherence_flow.py`` defines
    ``async def test_adherence_pipeline`` and opens ``AsyncSessionLocal``, so pytest
    collected it and ran it against ``medication.db`` -- the file this module's
    docstring says tests must never touch. It grew the real ``prescriptions`` table
    on every invocation, quietly, while reporting a pass.

    The guard hooks the production engine's ``connect`` event rather than patching
    ``AsyncSessionLocal``, because a module that did
    ``from app.database import AsyncSessionLocal`` holds its own reference and would
    sail straight past an attribute patch. Every session, however it was
    constructed, still has to open a connection on this one engine object.

    Nothing legitimate is blocked: endpoints get their session from the overridden
    ``get_db``, and the only production user of ``AsyncSessionLocal`` is
    ``scheduler_service``, which tests never start.
    """
    import app.database as appdb

    def _refuse(dbapi_connection, connection_record):
        raise RuntimeError(
            "This test tried to connect to the real database configured in "
            "settings.DATABASE_URL. Tests must use the `session` or `client` "
            "fixture, which are wired to a throwaway per-test SQLite file. "
            "Writing to medication.db destroys the data kept there for manual "
            "verification."
        )

    # Drop any pooled connection first: `connect` only fires for a genuinely new
    # DBAPI connection, so one already checked into the pool would otherwise slip
    # past the guard.
    appdb.engine.sync_engine.dispose()
    event.listen(appdb.engine.sync_engine, "connect", _refuse)
    try:
        yield
    finally:
        event.remove(appdb.engine.sync_engine, "connect", _refuse)


@pytest.fixture(autouse=True)
def forbid_live_ollama_in_tests(request, monkeypatch):
    """
    Ensure pytest tests do not accidentally hit the live Ollama daemon on loopback,
    causing 150s stalls per test in deterministic suites.
    Tests explicitly marked with @pytest.mark.live_llm retain access to the real daemon.
    """
    if "live_llm" in request.keywords:
        return
    from app.llm.client import ollama_client
    monkeypatch.setattr(ollama_client, "is_available", AsyncMock(return_value=False))


@pytest.fixture
async def engine(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    eng = create_async_engine(url, connect_args={"check_same_thread": False})

    # Mirrors app.database. SQLite ignores foreign keys unless asked, per
    # connection. This is not incidental to these tests: without it every
    # ondelete="CASCADE" is inert, so a test asserting that adherence history is
    # NOT cascaded away would pass for entirely the wrong reason.
    @event.listens_for(eng.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield eng
    await eng.dispose()


@pytest.fixture
def sessionmaker_for(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def session(sessionmaker_for):
    async with sessionmaker_for() as s:
        yield s


@pytest.fixture
async def client(sessionmaker_for):
    """An HTTP client wired to the test database."""
    from httpx import ASGITransport, AsyncClient

    from app.database import get_db
    from app.main import app

    async def _override_get_db():
        async with sessionmaker_for() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db

    # ASGITransport does not run lifespan, which is what we want here: lifespan
    # asserts the *real* database is stamped at Alembic head and starts the
    # reminder scheduler. Neither belongs in a test against a temp database.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()


async def _login(client, email, password):
    """Exchange credentials for an Authorization header."""
    # Login is form-encoded: the endpoint takes OAuth2PasswordRequestForm.
    r = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# The bootstrap ADMIN, created lazily and only when a test actually asks for a
# privileged account. Deliberately not created up front for every test: several tests
# count rows in ``users``, and an administrator nobody asked for would silently change
# what those counts mean.
_BOOTSTRAP_ADMIN = {
    # example.com, not .local: EmailStr rejects reserved TLDs, and the bootstrap goes
    # through AdminUserCreate on purpose so the test path and the CLI path validate
    # identically.
    "email": "bootstrap-admin@example.com",
    "name": "Bootstrap Admin",
    "password": "Passw0rd!",
}


@asynccontextmanager
async def _session_for(client):
    """A session on whatever database ``client`` is wired to.

    Borrows the app's own ``get_db`` override instead of taking a session parameter,
    so ``register`` stays a plain function and its twenty-odd call sites do not have
    to thread another fixture through.
    """
    from app.database import get_db
    from app.main import app

    async with asynccontextmanager(app.dependency_overrides[get_db])() as s:
        yield s


async def _bootstrap_admin_headers(client):
    """Create the first ADMIN if this database has none, and return its header.

    The first ADMIN cannot come from the API — ``POST /admin/users`` requires one to
    exist already — so it is created at the service layer. That is the same thing
    ``python -m app.cli create-admin`` does in a real deployment, and the reason that
    command exists.
    """
    from app.schemas.auth import AdminUserCreate, PrivilegedRole
    from app.services.auth_service import auth_service

    async with _session_for(client) as s:
        if await auth_service.get_user_by_email(s, _BOOTSTRAP_ADMIN["email"]) is None:
            await auth_service.create_privileged_user(
                s, AdminUserCreate(role=PrivilegedRole.ADMIN, **_BOOTSTRAP_ADMIN)
            )

    return await _login(
        client, _BOOTSTRAP_ADMIN["email"], _BOOTSTRAP_ADMIN["password"]
    )


async def register(client, email, role="PATIENT", password="Passw0rd!"):
    """Create a user of the given role and return an Authorization header for them.

    PATIENT goes through the public endpoint. Every other role goes through
    ``POST /admin/users`` as an ADMIN, because the public endpoint no longer accepts a
    role at all — see ``UserRegister``, where the field was removed rather than
    validated.

    So a test that merely *needs* a clinician gets one the way a deployment would.
    Tests about the authorization boundary itself live in ``test_auth_security.py``
    and deliberately do not use this helper: it would hide the thing they check.
    """
    name = email.split("@")[0]

    if role == "PATIENT":
        r = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "name": name},
        )
        assert r.status_code == 201, r.text
        return await _login(client, email, password)

    r = await client.post(
        "/api/v1/admin/users",
        json={"email": email, "password": password, "name": name, "role": role},
        headers=await _bootstrap_admin_headers(client),
    )
    assert r.status_code == 201, r.text
    return await _login(client, email, password)
