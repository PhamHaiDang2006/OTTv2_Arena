"""Persist casual human-versus-bot games separately from Arena matches."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('casual_games',
                    sa.Column('id', sa.UUID(), primary_key=True),
                    sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id'), nullable=False),
                    sa.Column('state', postgresql.JSONB(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_casual_games_user_id', 'casual_games', ['user_id'])


def downgrade():
    op.drop_table('casual_games')
