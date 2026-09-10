"""
Regression tests for registration atomicity.

The invariant under test: a registration either produces a complete account or no
account at all. There must never be a PATIENT row in ``users`` without its
matching row in ``patients``.

This used to be violable. ``register_user`` committed twice — the user, then the
profile — so anything that interrupted the gap (crash, dropped connection, worker
restart, or the profile insert simply failing) left a half-built account. The
failure mode is nasty precisely because it looks fine: login only reads ``users``,
so the credentials work and a token is issued, but every patient-scoped endpoint
resolves the profile via ``Patient.user_id`` and gets None. Filing a prescription
answers "User is not a patient", listing answers [], and schedules, reminders and
adherence have nothing to attach to. Nothing repairs it, and the user cannot
re-register because the email is now taken.
"""

import pytest
from sqlalchemy import func, select

import app.services.auth_service as auth_service_module
from app.models.patient import Patient
from app.models.user import User

CREDENTIALS = {"email": "newuser@example.com", "password": "Passw0rd!", "name": "New User"}


async def _count(session, model):
    """Row count read in a fresh transaction.

    The rollback matters: this session is separate from the one the request used,
    and without ending its current transaction SQLite can keep serving an older
    snapshot, which would make a committed row look absent.
    """
    await session.rollback()
    return (await session.execute(select(func.count()).select_from(model))).scalar()


async def test_patient_registration_creates_user_and_profile_together(client, session):
    """The happy path: a patient registration yields exactly one of each row."""
    r = await client.post("/api/v1/auth/register", json=CREDENTIALS)
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]

    assert await _count(session, User) == 1
    assert await _count(session, Patient) == 1

    rows = await session.execute(select(Patient).where(Patient.user_id == user_id))
    profile = rows.scalars().one()
    assert profile.user_id == user_id
    # Defaults have to land, since reminder resolution reads this column.
    assert profile.timezone == "UTC"


async def test_non_patient_role_gets_no_profile(client, session):
    """
    Only PATIENT has a profile table. Creating a clinician must not fabricate one,
    or clinician accounts would show up in patient-scoped queries.

    Routed through ``POST /admin/users`` because that is now the only way to create a
    clinician at all: the public endpoint has no ``role`` field. That also means this
    database ends up with two users — the bootstrap ADMIN the helper needed, and the
    CLINICIAN under test — and neither of them may have a patient profile.
    """
    from conftest import register

    await register(client, "clinician@example.com", "CLINICIAN")

    assert await _count(session, User) == 2, "expected the bootstrap ADMIN and the CLINICIAN"
    assert await _count(session, Patient) == 0


async def test_profile_failure_leaves_no_user_behind(client, session, monkeypatch):
    """
    The forced-failure rollback test.

    Profile creation is made to fail, and the assertion is that the user row does
    not survive it. Under the old two-commit implementation this fails: the user
    was already committed before the profile was ever attempted, so the count would
    be 1 and the orphaned account would be exactly the broken-but-plausible state
    described in the module docstring.
    """

    class ExplodingPatient:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("simulated failure while building the patient profile")

    monkeypatch.setattr(auth_service_module, "Patient", ExplodingPatient)

    with pytest.raises(RuntimeError, match="simulated failure"):
        await client.post("/api/v1/auth/register", json=CREDENTIALS)

    assert await _count(session, User) == 0, (
        "registration failed partway and left an orphaned user row: this account "
        "can log in but no patient endpoint will work for it"
    )
    assert await _count(session, Patient) == 0


async def test_failed_registration_leaves_the_email_reusable(client, session, monkeypatch):
    """
    The practical consequence of the rollback: the address is still free.

    If a failed attempt left the user row behind, the retry would be refused with
    "Email already registered" and the person would be permanently locked out of
    their own address.
    """

    class ExplodingPatient:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("simulated failure while building the patient profile")

    monkeypatch.setattr(auth_service_module, "Patient", ExplodingPatient)
    with pytest.raises(RuntimeError):
        await client.post("/api/v1/auth/register", json=CREDENTIALS)

    # Repair the world, then retry exactly as the user would.
    monkeypatch.setattr(auth_service_module, "Patient", Patient)
    r = await client.post("/api/v1/auth/register", json=CREDENTIALS)
    assert r.status_code == 201, r.text

    assert await _count(session, User) == 1
    assert await _count(session, Patient) == 1


async def test_duplicate_email_is_rejected_with_400(client, session):
    """A second registration of the same address is a client error, not a 500."""
    r = await client.post("/api/v1/auth/register", json=CREDENTIALS)
    assert r.status_code == 201, r.text

    r = await client.post("/api/v1/auth/register", json=CREDENTIALS)
    assert r.status_code == 400, r.text
    assert "already registered" in r.text

    assert await _count(session, User) == 1
    assert await _count(session, Patient) == 1


async def test_registered_patient_can_immediately_use_patient_endpoints(client):
    """
    Why the invariant matters, end to end.

    A complete account must be usable the instant registration returns. This is the
    test that would have caught the orphaned-profile bug in the field: it exercises
    the path that silently answers "User is not a patient" for a half-built account.
    """
    from datetime import date

    from conftest import register

    headers = await register(client, "patient@example.com", "PATIENT")
    r = await client.post(
        "/api/v1/prescriptions",
        json={
            "doctor_name": "Dr Who",
            "prescription_date": str(date.today()),
            "medications": [
                {"medicine_name": "Metformin", "strength": "500mg", "frequency": "twice daily"}
            ],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
