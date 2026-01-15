"""Initial migration

Revision ID: 001
Revises: 
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums
    op.execute("CREATE TYPE gamesource AS ENUM ('steam', 'itch')")
    op.execute("CREATE TYPE signaltype AS ENUM ('tag', 'keyword')")
    op.execute("CREATE TYPE pitchstatus AS ENUM ('new', 'scored', 'reviewed')")
    op.execute("CREATE TYPE verdict AS ENUM ('PASS', 'WATCH', 'TALK', 'INVEST')")

    # Create games table
    op.create_table('games',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source', postgresql.ENUM('steam', 'itch', name='gamesource', create_type=False), nullable=False),
        sa.Column('source_id', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('url', sa.String(length=1000), nullable=False),
        sa.Column('release_date', sa.Date(), nullable=True),
        sa.Column('price_eur', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('short_description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'source_id', name='uix_game_source_id')
    )
    op.create_index('ix_games_created_at', 'games', ['created_at'])
    op.create_index('ix_games_source', 'games', ['source'])

    # Create game_metrics_daily table
    op.create_table('game_metrics_daily',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('game_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('reviews_total', sa.Integer(), nullable=False),
        sa.Column('reviews_recent', sa.Integer(), nullable=False),
        sa.Column('rating_percent', sa.Integer(), nullable=True),
        sa.Column('followers', sa.Integer(), nullable=True),
        sa.Column('rank_signal', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('game_id', 'date', name='uix_game_metrics_game_date')
    )
    op.create_index('ix_game_metrics_date', 'game_metrics_daily', ['date'])

    # Create trends_daily table
    op.create_table('trends_daily',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('signal', sa.String(length=255), nullable=False),
        sa.Column('signal_type', postgresql.ENUM('tag', 'keyword', name='signaltype', create_type=False), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('avg_7d', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('delta_7d', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('velocity', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_trends_date_signal', 'trends_daily', ['date', 'signal'])
    op.create_index('ix_trends_velocity', 'trends_daily', ['velocity'])

    # Create pitches table
    op.create_table('pitches',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('dev_name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('studio_name', sa.String(length=255), nullable=True),
        sa.Column('team_size', sa.Integer(), nullable=False),
        sa.Column('released_before', sa.Boolean(), nullable=False),
        sa.Column('timeline_months', sa.Integer(), nullable=False),
        sa.Column('pitch_text', sa.Text(), nullable=False),
        sa.Column('hook_one_liner', sa.String(length=500), nullable=True),
        sa.Column('links', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('build_link', sa.String(length=1000), nullable=True),
        sa.Column('video_link', sa.String(length=1000), nullable=True),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', postgresql.ENUM('new', 'scored', 'reviewed', name='pitchstatus', create_type=False), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pitches_created_at', 'pitches', ['created_at'])
    op.create_index('ix_pitches_status', 'pitches', ['status'])

    # Create pitch_scores table
    op.create_table('pitch_scores',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pitch_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('score_total', sa.Integer(), nullable=False),
        sa.Column('score_hook', sa.Integer(), nullable=False),
        sa.Column('score_market', sa.Integer(), nullable=False),
        sa.Column('score_team', sa.Integer(), nullable=False),
        sa.Column('score_steam', sa.Integer(), nullable=False),
        sa.Column('score_asymmetry', sa.Integer(), nullable=False),
        sa.Column('verdict', postgresql.ENUM('PASS', 'WATCH', 'TALK', 'INVEST', name='verdict', create_type=False), nullable=False),
        sa.Column('why_yes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('why_no', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('next_step', sa.String(length=500), nullable=True),
        sa.Column('comparables', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['pitch_id'], ['pitches.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pitch_id')
    )
    op.create_index('ix_pitch_scores_verdict', 'pitch_scores', ['verdict'])


def downgrade() -> None:
    op.drop_index('ix_pitch_scores_verdict', table_name='pitch_scores')
    op.drop_table('pitch_scores')
    op.drop_index('ix_pitches_status', table_name='pitches')
    op.drop_index('ix_pitches_created_at', table_name='pitches')
    op.drop_table('pitches')
    op.drop_index('ix_trends_velocity', table_name='trends_daily')
    op.drop_index('ix_trends_date_signal', table_name='trends_daily')
    op.drop_table('trends_daily')
    op.drop_index('ix_game_metrics_date', table_name='game_metrics_daily')
    op.drop_table('game_metrics_daily')
    op.drop_index('ix_games_source', table_name='games')
    op.drop_index('ix_games_created_at', table_name='games')
    op.drop_table('games')
    op.execute("DROP TYPE verdict")
    op.execute("DROP TYPE pitchstatus")
    op.execute("DROP TYPE signaltype")
    op.execute("DROP TYPE gamesource")