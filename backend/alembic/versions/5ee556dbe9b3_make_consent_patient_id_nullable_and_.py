"""Make consent patient_id nullable and remove cascade

Revision ID: 5ee556dbe9b3
Revises: 6e0a180f741f
Create Date: 2026-08-31 11:07:23.993116

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ee556dbe9b3'
down_revision: Union[str, Sequence[str], None] = '6e0a180f741f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FK_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}

def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('consent_records', naming_convention=_FK_NAMING_CONVENTION) as batch_op:
        batch_op.alter_column('patient_id',
               existing_type=sa.INTEGER(),
               nullable=True)
        batch_op.drop_constraint('fk_consent_records_patient_id_patients', type_='foreignkey')
        batch_op.create_foreign_key(batch_op.f('fk_consent_records_patient_id_patients'), 'patients', ['patient_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('consent_records', naming_convention=_FK_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint('fk_consent_records_patient_id_patients', type_='foreignkey')
        batch_op.create_foreign_key('fk_consent_records_patient_id_patients', 'patients', ['patient_id'], ['id'], ondelete='CASCADE')
        batch_op.alter_column('patient_id',
               existing_type=sa.INTEGER(),
               nullable=False)

    # ### end Alembic commands ###
