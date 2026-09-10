"""rename the DOCTOR role to CLINICIAN

Revision ID: 9f2c1d7ab4e0
Revises: 86dcd2599328
Create Date: 2026-08-25 00:00:00.000000

A data migration, not a schema one. ``users.role`` is ``String(30)`` with no native
enum and no CHECK constraint, so retiring a role value is an UPDATE — there is no
type to alter and no constraint to rebuild. ``alembic check`` therefore reports
nothing here, which is expected: the model's column definition is unchanged.

Why rename at all: the codebase held one concept under two names. The role value said
DOCTOR while every docstring, analysis module and schema around it said "clinician".
That split is the precise shape of a lockout bug — update ``users.role`` to one term,
leave an authorization list checking the other, and legitimate accounts start getting
403s with nothing in the logs to explain it. CLINICIAN is also the more accurate word
for who performs review in this product; a pharmacist or nurse practitioner is not a
doctor.

CAREGIVER is deliberately *not* mapped by this migration. It had zero rows in every
database checked, no endpoint that granted it anything, and no client route. There is
nothing to migrate, so mapping it would invent data. It is simply gone from the
enums, which is what makes it unwritable going forward.

Note that ``prescriptions.doctor_name`` is untouched and unrelated: it holds a
prescriber's name as free text, not a role.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f2c1d7ab4e0'
down_revision: Union[str, Sequence[str], None] = '86dcd2599328'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """DOCTOR -> CLINICIAN."""
    # Parameter-bound rather than interpolated, and scoped by an exact-match WHERE so
    # PATIENT, ADMIN and any unexpected value are left exactly as they are.
    op.execute(
        sa.text("UPDATE users SET role = 'CLINICIAN' WHERE role = 'DOCTOR'")
    )


def downgrade() -> None:
    """CLINICIAN -> DOCTOR.

    Written out explicitly rather than left as a no-op. A downgrade that silently
    keeps CLINICIAN rows would strand them: the pre-migration code checks for
    "DOCTOR", so every clinician account would authenticate fine and then be refused
    by every clinician-protected route.

    This is not perfectly lossless, and the imprecision is worth stating. If a
    CLINICIAN row is created *after* this upgrade runs, a downgrade relabels it DOCTOR
    even though it was never a DOCTOR to begin with. That is the correct trade —
    matching the schema the older code expects beats preserving a distinction that
    code cannot act on — but it means upgrade/downgrade/upgrade is idempotent in
    effect, not an audit-preserving round trip.
    """
    op.execute(
        sa.text("UPDATE users SET role = 'DOCTOR' WHERE role = 'CLINICIAN'")
    )
