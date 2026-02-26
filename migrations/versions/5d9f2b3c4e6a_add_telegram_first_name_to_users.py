"""add_telegram_first_name_to_users

Revision ID: 5d9f2b3c4e6a
Revises: 4c8e1a2b3d5f
Create Date: 2026-02-26 18:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d9f2b3c4e6a'
down_revision: Union[str, None] = '4c8e1a2b3d5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('telegram_first_name', sa.String(length=255), nullable=True))
    # Backfill: copy existing first_name to telegram_first_name for current users
    op.execute("UPDATE users SET telegram_first_name = first_name WHERE telegram_first_name IS NULL")


def downgrade() -> None:
    op.drop_column('users', 'telegram_first_name')
