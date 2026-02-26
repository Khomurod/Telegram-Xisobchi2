"""add_city_to_users

Revision ID: 4c8e1a2b3d5f
Revises: 2a6998f8e5d4
Create Date: 2026-02-26 13:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c8e1a2b3d5f'
down_revision: Union[str, None] = '2a6998f8e5d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('city', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'city')
