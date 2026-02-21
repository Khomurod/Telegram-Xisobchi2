"""change_created_at_to_timezone_aware

Revision ID: 31d4bbd56297
Revises: ab1e558f6c71
Create Date: 2026-02-21 19:06:40.362550

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31d4bbd56297'
down_revision: Union[str, None] = 'ab1e558f6c71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get the database dialect
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'postgresql':
        # Convert TIMESTAMP WITHOUT TIME ZONE → TIMESTAMP WITH TIME ZONE
        # and FLOAT → NUMERIC(18,2) for the amount column
        op.execute(
            "ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMPTZ "
            "USING created_at AT TIME ZONE 'UTC'"
        )
        op.execute(
            "ALTER TABLE transactions ALTER COLUMN created_at TYPE TIMESTAMPTZ "
            "USING created_at AT TIME ZONE 'UTC'"
        )
        op.alter_column('transactions', 'amount',
                        existing_type=sa.FLOAT(),
                        type_=sa.Numeric(precision=18, scale=2),
                        existing_nullable=False)
    # SQLite: no-op — SQLite stores everything as text anyway
    # and doesn't enforce column types


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'postgresql':
        op.execute(
            "ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMP "
            "USING created_at AT TIME ZONE 'UTC'"
        )
        op.execute(
            "ALTER TABLE transactions ALTER COLUMN created_at TYPE TIMESTAMP "
            "USING created_at AT TIME ZONE 'UTC'"
        )
        op.alter_column('transactions', 'amount',
                        existing_type=sa.Numeric(precision=18, scale=2),
                        type_=sa.FLOAT(),
                        existing_nullable=False)
