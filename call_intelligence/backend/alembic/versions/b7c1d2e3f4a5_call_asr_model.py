"""calls.asr_model: which engine transcribed the call

Revision ID: b7c1d2e3f4a5
Revises: 93e5104e1f87
"""
import sqlalchemy as sa
from alembic import op

revision = "b7c1d2e3f4a5"
down_revision = "93e5104e1f87"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("calls", sa.Column("asr_model", sa.String(80), nullable=False, server_default=""))


def downgrade():
    op.drop_column("calls", "asr_model")
