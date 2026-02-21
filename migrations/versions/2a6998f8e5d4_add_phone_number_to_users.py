"""add_phone_number_to_users

Revision ID: 2a6998f8e5d4
Revises: 31d4bbd56297
Create Date: 2026-02-21 22:35:11.593503

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a6998f8e5d4'
down_revision: Union[str, None] = '31d4bbd56297'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone_number', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'phone_number')
