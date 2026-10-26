"""Public cosmetics and immutable per-round results for personal statistics."""
import sqlalchemy as sa
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('player_profiles',
                    sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id'), primary_key=True),
                    sa.Column('display_name', sa.String(40), nullable=False),
                    sa.Column('bio', sa.String(240), nullable=False),
                    sa.Column('avatar', sa.String(16), nullable=False),
                    sa.Column('frame', sa.String(16), nullable=False),
                    sa.Column('color', sa.String(16), nullable=False))
    op.create_table('room_results',
                    sa.Column('room_id', sa.UUID(), sa.ForeignKey('play_rooms.id'), primary_key=True),
                    sa.Column('round', sa.Integer(), primary_key=True),
                    sa.Column('map', sa.String(16), nullable=False),
                    sa.Column('blue_id', sa.UUID(), sa.ForeignKey('users.id'), nullable=False),
                    sa.Column('red_id', sa.UUID(), sa.ForeignKey('users.id'), nullable=False),
                    sa.Column('winner_id', sa.UUID(), sa.ForeignKey('users.id'), nullable=False))
    op.create_index('ix_room_results_blue_id', 'room_results', ['blue_id'])
    op.create_index('ix_room_results_red_id', 'room_results', ['red_id'])
    # Old rematches overwrote prior rounds; recover only the terminal round still present.
    op.execute("""
      INSERT INTO room_results (room_id, round, map, blue_id, red_id, winner_id)
      SELECT r.id, (r.state->>'round')::integer, r.state->>'map',
             (b->>'id')::uuid, (d->>'id')::uuid,
             CASE WHEN r.state->'result'->>'winner' = 'BLUE' THEN (b->>'id')::uuid ELSE (d->>'id')::uuid END
      FROM play_rooms r
      CROSS JOIN LATERAL jsonb_array_elements(r.state->'players') b
      CROSS JOIN LATERAL jsonb_array_elements(r.state->'players') d
      WHERE b->>'side' = 'BLUE' AND d->>'side' = 'RED'
        AND r.state->>'status' IN ('finished', 'closed')
        AND r.state->'result'->>'winner' IN ('BLUE', 'RED')
      ON CONFLICT DO NOTHING
    """)


def downgrade():
    op.drop_table('room_results')
    op.drop_table('player_profiles')
