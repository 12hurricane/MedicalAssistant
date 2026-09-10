"""replace medication_schedules.active with a lifecycle status, and protect adherence history

Revision ID: c7e4b91a53d8
Revises: 9f2c1d7ab4e0
Create Date: 2026-08-26 00:00:00.000000

Two changes that only make sense together.

**1. ``active`` (BOOLEAN) becomes ``status`` (VARCHAR(20)).**

The boolean was answering four questions and getting one wrong. ``active=True`` meant
"not explicitly retired" rather than "live" --- a course that ended last month kept
``active=True`` forever, because both consumers re-filter on the course dates at query
time. And ``active=False`` collapsed "the clinician discontinued this medication" with
"a newer schedule replaced this row": clinically opposite facts, indistinguishable
afterwards. A reviewer looking at a gap in adherence could not tell whether the patient
was taken off the drug or the dose time simply moved.

The column now holds ACTIVE, CANCELLED or SUPERSEDED, and a CHECK constraint enforces
that list. COMPLETED is deliberately *not* storable: it is derived from ``end_date``
(``MedicationSchedule.lifecycle_on``), because a stored COMPLETED would need a job to
notice the day a course ends --- a job that can fail, be forgotten, or run in the wrong
timezone, leaving the column stale in exactly the way ``active`` already was.

The backfill maps every retired row to SUPERSEDED rather than guessing between the two
reasons. That is the honest direction: SUPERSEDED asserts only "no longer the current
plan", which is true of every ``active=False`` row, whereas CANCELLED would assert a
clinical decision that the old column never actually recorded. Rows retired from here on
get the accurate value.

**2. ``medication_events.schedule_id`` goes from ON DELETE CASCADE to RESTRICT.**

This is the change that makes point 1 enforceable instead of merely intended.
``medication_events`` is the patient's adherence history --- what they took, what they
missed, and why. It is derived from nothing and it is the sole input to the adherence
score, so a deleted event is gone. With CASCADE, ``DELETE FROM medication_schedules
WHERE id = 36`` silently erased eight logged doses, and deleting one
``prescribed_medications`` row erased all fourteen schedules and all fifty-six events,
in both cases without an error. Verified against a copy of the live database before
writing this.

One constraint covers the whole chain, because the CASCADEs above it now terminate here:

    DELETE a medication_schedule    -> refused directly
    DELETE a prescribed_medication  -> refused (its CASCADE into schedules trips this)
    DELETE a prescription           -> refused, transitively, by the same path
    DELETE a patient                -> still permitted

That last line is deliberate. Events cascade from ``patients`` on their own FK, so
erasing a patient still works: a data-protection obligation must not be blocked by a
foreign key. What is blocked is every *narrower* delete, which is where the accidents
happen.

``reminders.schedule_id`` keeps CASCADE. A reminder records that a phone was told to
buzz; the dose it was about lives in ``medication_events``. Nothing reviews reminders
after the fact.

No API change: ``MedicationSchedule.active`` appeared in no response schema, so
``openapi.json`` and the generated Flutter models are untouched by this revision.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e4b91a53d8'
down_revision: Union[str, Sequence[str], None] = '9f2c1d7ab4e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# SQLite cannot ALTER a foreign key, so batch mode rebuilds the table. Dropping the
# existing FK requires a name, and the baseline created it unnamed, so a naming
# convention is supplied for Alembic to derive one from the reflected columns. This is
# the documented recipe for exactly this situation.
_FK_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}
_EVENT_SCHEDULE_FK = "fk_medication_events_schedule_id_medication_schedules"

# Kept as a literal rather than imported from app.models. A migration has to keep
# describing the schema as it was at this revision; importing the enum would let a later
# edit to application code retroactively change what this file does. The model renders
# the identical SQL from ``STORED_SCHEDULE_STATUSES``, and a test asserts both paths
# produce a database that refuses a stored COMPLETED.
_STORED_STATUS_CHECK = "status IN ('ACTIVE', 'CANCELLED', 'SUPERSEDED')"


def upgrade() -> None:
    # --- 1. active -> status -------------------------------------------------------
    # Added nullable, then backfilled, then tightened. Adding it NOT NULL in one step
    # would need a server default, and alembic/env.py runs with
    # compare_server_default=True: a default in the database that the model does not
    # declare is a permanent `alembic check` diff.
    op.add_column(
        "medication_schedules",
        sa.Column("status", sa.String(length=20), nullable=True),
    )

    op.execute(
        sa.text(
            "UPDATE medication_schedules "
            "SET status = CASE WHEN active = 1 THEN 'ACTIVE' ELSE 'SUPERSEDED' END"
        )
    )

    with op.batch_alter_table("medication_schedules") as batch_op:
        batch_op.alter_column(
            "status", existing_type=sa.String(length=20), nullable=False
        )
        batch_op.create_check_constraint("ck_schedule_status_stored", _STORED_STATUS_CHECK)
        batch_op.drop_column("active")

    # --- 2. adherence history stops cascading -------------------------------------
    with op.batch_alter_table(
        "medication_events", naming_convention=_FK_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint(_EVENT_SCHEDULE_FK, type_="foreignkey")
        # Recreated under the same derived name. Alembic rejects an unnamed constraint
        # here (`ValueError: Constraint must have a name`), so a migrated database ends
        # up with a named FK where `create_all` leaves it unnamed. That asymmetry is
        # cosmetic: autogenerate compares foreign keys on their column/table/ondelete
        # signature, not their name, which `test_models_match_migrations` verifies by
        # running `alembic check` against this revision.
        batch_op.create_foreign_key(
            _EVENT_SCHEDULE_FK,
            "medication_schedules",
            ["schedule_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """status -> active, and RESTRICT -> CASCADE.

    Written out rather than left as a no-op, because the pre-migration code reads
    ``MedicationSchedule.active``: leaving ``status`` in place would make every
    schedule query fail on a missing column.

    Lossy in one direction, and worth stating plainly. CANCELLED and SUPERSEDED both
    become ``active = 0``, so the distinction this revision exists to record is
    destroyed by going back --- there is no boolean that can hold it. Re-upgrading maps
    those rows to SUPERSEDED, matching the original backfill, so
    upgrade/downgrade/upgrade is idempotent in effect but not an audit-preserving round
    trip.

    Restoring CASCADE also restores the silent-deletion behaviour. That is what the
    older schema was, and a downgrade's job is to reproduce it, not to improve on it.
    """
    op.add_column(
        "medication_schedules",
        sa.Column("active", sa.Boolean(), nullable=True),
    )

    op.execute(
        sa.text(
            "UPDATE medication_schedules "
            "SET active = CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END"
        )
    )

    with op.batch_alter_table("medication_schedules") as batch_op:
        batch_op.alter_column("active", existing_type=sa.Boolean(), nullable=False)
        # Dropped explicitly, and before the column. SQLite's batch mode rebuilds the
        # table from reflection, and it *does* reflect CHECK constraints -- so leaving
        # this implicit emits `CHECK (status IN (...))` on a table that no longer has a
        # status column, and the rebuild fails with "no such column".
        batch_op.drop_constraint("ck_schedule_status_stored", type_="check")
        batch_op.drop_column("status")

    with op.batch_alter_table(
        "medication_events", naming_convention=_FK_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint(_EVENT_SCHEDULE_FK, type_="foreignkey")
        batch_op.create_foreign_key(
            _EVENT_SCHEDULE_FK,
            "medication_schedules",
            ["schedule_id"],
            ["id"],
            ondelete="CASCADE",
        )
