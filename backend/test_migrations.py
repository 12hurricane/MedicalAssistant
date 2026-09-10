"""
Migration tests.

``conftest.py`` builds the test schema with ``Base.metadata.create_all`` rather
than by running the migrations, for speed. That shortcut is only defensible while
the two provably agree, and this module is what provides the proof —
``test_models_match_migrations`` is the check that conftest's docstring points at.

Everything here runs Alembic in a subprocess against a throwaway SQLite file. Two
reasons that is not merely convenient:

- ``alembic/env.py`` ends in ``asyncio.run(...)``, which raises if called from
  inside a running event loop, so it cannot be driven from an async test.
- ``env.py`` deliberately takes its URL from ``settings.DATABASE_URL`` rather than
  ``alembic.ini``, so the only honest way to point it elsewhere is the environment
  — which is also exactly how CI would run it.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).parent

# Tables Alembic owns rather than the application.
BOOKKEEPING = {"alembic_version"}


def _alembic(tmp_db: Path, *args: str) -> subprocess.CompletedProcess:
    """Run an alembic command against ``tmp_db``, never the real database."""
    env = dict(os.environ)
    # Environment beats .env in pydantic-settings, so this overrides the real URL.
    # as_posix() matters on Windows: a URL with backslashes is not parsed as a path.
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db.as_posix()}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )


def _tables(tmp_db: Path) -> set[str]:
    con = sqlite3.connect(tmp_db)
    try:
        rows = con.execute(
            "select name from sqlite_master "
            "where type='table' and name not like 'sqlite_%'"
        ).fetchall()
    finally:
        con.close()
    return {r[0] for r in rows} - BOOKKEEPING


@pytest.fixture
def fresh_db(tmp_path):
    return tmp_path / "migrations.db"


def test_upgrade_from_empty_reaches_head(fresh_db):
    """A brand-new database can be brought up by migrations alone."""
    up = _alembic(fresh_db, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    current = _alembic(fresh_db, "current")
    assert current.returncode == 0, current.stderr
    assert "(head)" in current.stdout, current.stdout

    tables = _tables(fresh_db)
    # Spot-check the tables the medication flow cannot work without, rather than
    # pinning the full list, which would break on every legitimate new model.
    for expected in (
        "users",
        "patients",
        "prescriptions",
        "prescribed_medications",
        "medication_schedules",
        "medication_events",
    ):
        assert expected in tables, f"{expected} missing after upgrade: {sorted(tables)}"


def test_models_match_migrations(fresh_db):
    """
    The invariant conftest relies on: models, migration history and the resulting
    schema all agree.

    ``alembic check`` autogenerates against the live schema and fails if it finds
    any operation still to apply. A drift here means either a model changed without
    a migration, or a migration does not reproduce the models — and in that state
    ``create_all`` in conftest would be building a schema the real database does
    not have, so tests would be passing against a fiction.
    """
    up = _alembic(fresh_db, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    check = _alembic(fresh_db, "check")
    assert check.returncode == 0, (
        "models have drifted from the migration history:\n"
        f"stdout:\n{check.stdout}\nstderr:\n{check.stderr}"
    )
    assert "No new upgrade operations detected" in check.stdout, check.stdout


def test_downgrade_to_base_removes_the_application_schema(fresh_db):
    """
    The migration is reversible. A downgrade path that does not work is a migration
    you cannot roll back in an incident, which is when you most need to.
    """
    assert _alembic(fresh_db, "upgrade", "head").returncode == 0
    assert _tables(fresh_db), "upgrade produced no tables"

    down = _alembic(fresh_db, "downgrade", "base")
    assert down.returncode == 0, down.stderr
    assert _tables(fresh_db) == set(), (
        f"downgrade left tables behind: {sorted(_tables(fresh_db))}"
    )


def test_upgrade_downgrade_upgrade_is_repeatable(fresh_db):
    """
    A full round trip leaves the same schema it started with.

    This catches the classic asymmetric migration: a downgrade that drops less than
    the upgrade created, so the second upgrade collides with a leftover object.
    """
    assert _alembic(fresh_db, "upgrade", "head").returncode == 0
    first = _tables(fresh_db)

    assert _alembic(fresh_db, "downgrade", "base").returncode == 0
    second_up = _alembic(fresh_db, "upgrade", "head")
    assert second_up.returncode == 0, second_up.stderr

    assert _tables(fresh_db) == first, (
        "schema after a downgrade/upgrade round trip differs from the original"
    )
    check = _alembic(fresh_db, "check")
    assert check.returncode == 0, check.stdout + check.stderr


# ---------------------------------------------------------------------------
# 9f2c1d7ab4e0 — DOCTOR -> CLINICIAN
# ---------------------------------------------------------------------------

# The revision immediately before the rename. Stopping here gives a database on the
# old schema with the old vocabulary, which is the only state in which the data
# migration has anything to do. Named rather than expressed as "head-1" because a
# relative target would silently start testing a different migration as history grows.
BEFORE_RENAME = "86dcd2599328"
RENAME = "9f2c1d7ab4e0"


def _insert_user(tmp_db: Path, email: str, role: str) -> None:
    """Insert a bare users row directly, bypassing the application.

    Deliberately not through the API: the point is to simulate rows that already
    existed *before* the rename shipped, which the current code can no longer create.

    Dynamically checks whether ``token_version`` exists in the schema so that the
    same helper works both before and after the token-version migration.
    """
    con = sqlite3.connect(tmp_db)
    try:
        cols = {row[1] for row in con.execute("pragma table_info(users)").fetchall()}
        if "token_version" in cols:
            con.execute(
                "insert into users (name, email, hashed_password, role, is_active, token_version) "
                "values (?, ?, 'x', ?, 1, 1)",
                (email.split("@")[0], email, role),
            )
        else:
            con.execute(
                "insert into users (name, email, hashed_password, role, is_active) "
                "values (?, ?, 'x', ?, 1)",
                (email.split("@")[0], email, role),
            )
        con.commit()
    finally:
        con.close()


def _roles(tmp_db: Path) -> dict[str, str]:
    con = sqlite3.connect(tmp_db)
    try:
        return dict(con.execute("select email, role from users").fetchall())
    finally:
        con.close()


def test_existing_doctor_rows_become_clinician(fresh_db):
    """The data migration does what its name says, and only that.

    A schema-only view of this migration is empty — ``users.role`` is a ``String(30)``
    with no enum and no CHECK constraint, so ``alembic check`` has nothing to report
    and every other test in this module would pass whether the UPDATE ran or not. This
    is the only test that observes the row.

    The two control rows matter as much as the subject: a migration written as
    ``UPDATE users SET role = 'CLINICIAN'`` with a missing or wrong WHERE clause would
    make every account a clinician, which is a privilege escalation across the entire
    user table and would otherwise ship looking like a successful rename.
    """
    assert _alembic(fresh_db, "upgrade", BEFORE_RENAME).returncode == 0

    _insert_user(fresh_db, "legacy-doctor@example.com", "DOCTOR")
    _insert_user(fresh_db, "legacy-patient@example.com", "PATIENT")
    _insert_user(fresh_db, "legacy-admin@example.com", "ADMIN")

    up = _alembic(fresh_db, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    roles = _roles(fresh_db)
    assert roles["legacy-doctor@example.com"] == "CLINICIAN", (
        "the DOCTOR row was not migrated; that account would authenticate and then be "
        "refused by every clinician-protected route"
    )
    assert roles["legacy-patient@example.com"] == "PATIENT"
    assert roles["legacy-admin@example.com"] == "ADMIN"


def test_the_rename_is_reversible(fresh_db):
    """Downgrade puts CLINICIAN back to DOCTOR, and leaves the others alone.

    Not a formality. The pre-rename code compares against ``"DOCTOR"``, so a downgrade
    that left CLINICIAN rows in place would strand every clinician account behind a
    403 — the exact lockout the rename exists to prevent, arrived at from the other
    direction.
    """
    assert _alembic(fresh_db, "upgrade", "head").returncode == 0

    _insert_user(fresh_db, "clinician@example.com", "CLINICIAN")
    _insert_user(fresh_db, "patient@example.com", "PATIENT")

    down = _alembic(fresh_db, "downgrade", BEFORE_RENAME)
    assert down.returncode == 0, down.stderr

    roles = _roles(fresh_db)
    assert roles["clinician@example.com"] == "DOCTOR"
    assert roles["patient@example.com"] == "PATIENT"


def test_caregiver_rows_are_left_untouched(fresh_db):
    """CAREGIVER is retired, not remapped — and the migration must not invent a role.

    CAREGIVER had zero rows anywhere, so there was nothing to migrate, and guessing a
    destination for a role that granted no access would be fabricating clinical
    authorization out of an empty set. The value is unwritable going forward because it
    is absent from the enums (``test_role_vocabulary.py``); a row that somehow predates
    that is left exactly as found, where it is visible, rather than quietly promoted to
    CLINICIAN by a rename it has nothing to do with.
    """
    assert _alembic(fresh_db, "upgrade", BEFORE_RENAME).returncode == 0
    _insert_user(fresh_db, "legacy-caregiver@example.com", "CAREGIVER")

    assert _alembic(fresh_db, "upgrade", "head").returncode == 0

    assert _roles(fresh_db)["legacy-caregiver@example.com"] == "CAREGIVER"


# --------------------------------------------------------------------------------------
# c7e4b91a53d8 — medication_schedules.active becomes a lifecycle status
# --------------------------------------------------------------------------------------

# The revision immediately before the lifecycle change, for the same reason
# BEFORE_RENAME is named rather than computed.
BEFORE_LIFECYCLE = "9f2c1d7ab4e0"
LIFECYCLE = "c7e4b91a53d8"


def _insert_legacy_schedule(tmp_db: Path, *, slot: str, active: int) -> None:
    """Insert a pre-lifecycle medication_schedules row directly.

    ``sqlite3`` connections have ``foreign_keys`` OFF by default, so the parent chain
    (user -> patient -> prescription -> prescribed_medication) can be skipped: this test
    is about one column's values, and building four unrelated rows to satisfy constraints
    that are not enforced here would only add ways for it to break for the wrong reason.
    """
    con = sqlite3.connect(tmp_db)
    try:
        con.execute(
            "insert into medication_schedules "
            "(prescribed_medication_id, patient_id, scheduled_time, start_date, active) "
            "values (1, 1, ?, '2026-03-01', ?)",
            (slot, active),
        )
        con.commit()
    finally:
        con.close()


def _schedule_column(tmp_db: Path, column: str) -> dict[str, object]:
    con = sqlite3.connect(tmp_db)
    try:
        return dict(
            con.execute(
                f"select scheduled_time, {column} from medication_schedules"
            ).fetchall()
        )
    finally:
        con.close()


def _delete_rules(tmp_db: Path, table: str) -> dict[str, str]:
    """Map each of ``table``'s foreign key columns to its ON DELETE action.

    ``pragma foreign_key_list`` yields
    ``(id, seq, referenced_table, from_column, to_column, on_update, on_delete, match)``.
    Keyed on the local column rather than the referenced table because that is what the
    model declares, and because a table can point at the same parent twice.
    """
    con = sqlite3.connect(tmp_db)
    try:
        return {
            row[3]: row[6]
            for row in con.execute(f"pragma foreign_key_list({table})")
        }
    finally:
        con.close()


def test_the_status_backfill_preserves_liveness(fresh_db):
    """A live schedule stays live across the upgrade; a retired one stays retired.

    The one thing this migration must not do is change which doses a patient is being
    reminded about. Both consumers filter on the status column, so mapping a live row to
    a retired value silently stops a medication, and mapping a retired row to ACTIVE
    silently restarts one the clinician had already stopped. The second is the more
    dangerous direction.

    Retired rows become SUPERSEDED rather than CANCELLED deliberately: SUPERSEDED claims
    only "no longer the current plan", which is true of every ``active = 0`` row, while
    CANCELLED would assert a clinical decision the old boolean never recorded.
    """
    assert _alembic(fresh_db, "upgrade", BEFORE_LIFECYCLE).returncode == 0

    _insert_legacy_schedule(fresh_db, slot="08:00:00", active=1)
    _insert_legacy_schedule(fresh_db, slot="20:00:00", active=0)

    up = _alembic(fresh_db, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    assert _schedule_column(fresh_db, "status") == {
        "08:00:00": "ACTIVE",
        "20:00:00": "SUPERSEDED",
    }


def test_the_migrated_schema_refuses_a_stored_completed(fresh_db):
    """The CHECK constraint exists in a migrated database, not only in ``create_all``.

    Worth its own test because the two schemas are built by different code. The model
    renders the constraint from ``STORED_SCHEDULE_STATUSES``; the migration carries a
    hand-written literal, so that an edit to application code cannot retroactively
    change what an applied revision did. Those are two chances to disagree, and
    ``alembic check`` cannot catch the disagreement: autogenerate does not compare CHECK
    constraints at all. This does.
    """
    assert _alembic(fresh_db, "upgrade", "head").returncode == 0

    con = sqlite3.connect(fresh_db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "insert into medication_schedules "
                "(prescribed_medication_id, patient_id, scheduled_time, start_date, status) "
                "values (1, 1, '08:00:00', '2026-03-01', 'COMPLETED')"
            )
            con.commit()
    finally:
        con.close()


def test_the_migration_makes_event_deletes_restrict(fresh_db):
    """``medication_events.schedule_id`` is RESTRICT in a migrated database.

    Read from the schema rather than by attempting a delete: the behavioural proof lives
    in ``test_schedule_lifecycle.py`` against a ``create_all`` database, and what is
    unproven there is that the *migration* produced the same DDL — SQLite cannot ALTER a
    foreign key, so this revision rebuilds the table, which is the step that could
    silently drop the clause.

    ``reminders`` is asserted alongside it. It keeps CASCADE by design, so a blanket
    find-and-replace of the ondelete clause would look like a success here without it.
    """
    assert _alembic(fresh_db, "upgrade", "head").returncode == 0

    events = _delete_rules(fresh_db, "medication_events")
    reminders = _delete_rules(fresh_db, "reminders")

    assert events["schedule_id"] == "RESTRICT", (
        "adherence history still cascades away with its schedule"
    )
    assert events["patient_id"] == "CASCADE", (
        "erasing a patient must stay possible; only the narrower deletes are blocked"
    )
    assert reminders["schedule_id"] == "CASCADE", (
        "reminders are notification artefacts, not clinical history"
    )


def test_the_lifecycle_change_is_reversible(fresh_db):
    """Downgrade restores the boolean, collapsing both retired states to 0.

    Lossy on purpose, and asserted as such: no boolean can hold the CANCELLED/SUPERSEDED
    distinction, so going back destroys it. What must survive is liveness, because the
    pre-migration code reads ``active`` to decide what to dispatch.
    """
    assert _alembic(fresh_db, "upgrade", "head").returncode == 0

    con = sqlite3.connect(fresh_db)
    try:
        for slot, status in (
            ("08:00:00", "ACTIVE"),
            ("14:00:00", "CANCELLED"),
            ("20:00:00", "SUPERSEDED"),
        ):
            con.execute(
                "insert into medication_schedules "
                "(prescribed_medication_id, patient_id, scheduled_time, start_date, status) "
                "values (1, 1, ?, '2026-03-01', ?)",
                (slot, status),
            )
        con.commit()
    finally:
        con.close()

    down = _alembic(fresh_db, "downgrade", BEFORE_LIFECYCLE)
    assert down.returncode == 0, down.stderr

    assert _schedule_column(fresh_db, "active") == {
        "08:00:00": 1,
        "14:00:00": 0,
        "20:00:00": 0,
    }
