"""Durable private two-player rooms, independent of Arena queues."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('play_rooms',
                    sa.Column('id', sa.UUID(), primary_key=True),
                    sa.Column('code', sa.String(8), nullable=False, unique=True),
                    sa.Column('host_id', sa.UUID(), sa.ForeignKey('users.id'), nullable=False),
                    sa.Column('guest_id', sa.UUID(), sa.ForeignKey('users.id'), nullable=True),
                    sa.Column('state', postgresql.JSONB(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_play_rooms_host_id', 'play_rooms', ['host_id'])
    op.create_index('ix_play_rooms_guest_id', 'play_rooms', ['guest_id'])


def downgrade():
    op.drop_table('play_rooms')
