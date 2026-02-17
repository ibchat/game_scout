"""add voy methodology table

Revision ID: 008_voy_methodology
Revises: 007_voy_learning
Create Date: 2026-02-03 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008_voy_methodology'
down_revision = '007_voy_learning'
branch_labels = None
depends_on = None


def upgrade():
    # voy_methodology - нормативная методология Bonfire (read-only)
    op.create_table(
        'voy_methodology',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('version', sa.Text(), nullable=False, server_default='1.0'),
        sa.Column('title', sa.Text(), nullable=False, server_default='Bonfire Methodology'),
        sa.Column('content_json', postgresql.JSONB(), nullable=False),  # Структурированное содержание
        sa.Column('content_text', sa.Text(), nullable=False),  # Полный текст для отображения
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_readonly', sa.Boolean(), nullable=False, server_default='true'),  # Всегда true
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # voy_override - логи переопределений решений инвестором
    op.create_table(
        'voy_override',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_item_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('system_recommendation', sa.Text(), nullable=False),
        sa.Column('user_decision', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_voy_override_run_item_id', 'voy_override', ['run_item_id'])
    op.create_index('idx_voy_override_created_at', 'voy_override', ['created_at'])
    op.create_foreign_key(
        'fk_voy_override_run_item',
        'voy_override', 'voy_run_item',
        ['run_item_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Создаем дефолтную методологию Bonfire
    methodology_text = """BONFIRE METHODOLOGY - Нормативный документ

═══════════════════════════════════════════════════════════════

1. ПРИНЦИП ИНВЕСТИЦИОННОЙ ДИСЦИПЛИНЫ

VOY является инструментом поддержки принятия решений, но не принимает инвестиционных решений самостоятельно. Все решения принимаются инвестором на основе анализа данных и рекомендаций системы.

VOY предоставляет информацию, скоринг и рекомендации, но финальное решение всегда остается за инвестором.

═══════════════════════════════════════════════════════════════

2. ПРИНЦИП ПРОЗРАЧНОСТИ

Все алгоритмы скоринга, веса skills и изменения в системе должны быть прозрачными и объяснимыми. Каждое изменение весов логируется с указанием причины и источника.

Система должна обеспечивать полную прослеживаемость всех вычислений и решений.

═══════════════════════════════════════════════════════════════

3. ПРИНЦИП КОНТРОЛИРУЕМОГО ОБУЧЕНИЯ

Обучение системы возможно только при явном разрешении (learning_enabled = true). Замороженные skills (frozen_skills) никогда не изменяются, независимо от feedback или GPT advice.

Обучение происходит только в рамках установленных лимитов и правил.

═══════════════════════════════════════════════════════════════

4. ПРИНЦИП НЕИЗМЕННОСТИ МЕТОДОЛОГИИ

Методология Bonfire является нормативным документом и не может быть изменена системой, GPT или автоматически. Изменения возможны только администратором вручную.

Методология определяет правила работы системы и не участвует в обучении.

═══════════════════════════════════════════════════════════════

5. ПРИНЦИП ПРИОРИТЕТА ИНВЕСТОРА

Инвестор всегда имеет право переопределить решение системы (override). Все override фиксируются в логах с указанием причины и времени.

Инвестор всегда главный. Система поддерживает, но не заменяет человеческое решение.

═══════════════════════════════════════════════════════════════

6. ПРИНЦИП ОГРАНИЧЕННОГО ИСПОЛЬЗОВАНИЯ GPT

ChatGPT используется исключительно как аналитический советник. GPT не имеет права добавлять skills, менять стратегию, thresholds или методологию. Все ответы GPT валидируются строго по JSON-шаблону.

GPT не может изменять архитектуру системы или нормативные документы.

═══════════════════════════════════════════════════════════════

7. ПРИНЦИП АУДИТА И ОТВЕТСТВЕННОСТИ

Все действия системы, изменения весов, override решения и GPT advice должны быть залогированы и доступны для аудита. Система должна обеспечивать полную прослеживаемость всех решений.

Каждое действие должно быть объяснимо и залогировано."""
    
    op.execute(f"""
        INSERT INTO voy_methodology (id, version, title, content_json, content_text, is_active, is_readonly)
        VALUES (
            gen_random_uuid(),
            '1.0',
            'Bonfire Methodology',
            '{{"sections": [{{"id": 1, "title": "Принцип инвестиционной дисциплины"}}, {{"id": 2, "title": "Принцип прозрачности"}}, {{"id": 3, "title": "Принцип контролируемого обучения"}}, {{"id": 4, "title": "Принцип неизменности методологии"}}, {{"id": 5, "title": "Принцип приоритета инвестора"}}, {{"id": 6, "title": "Принцип ограниченного использования GPT"}}, {{"id": 7, "title": "Принцип аудита и ответственности"}}]}}'::jsonb,
            {repr(methodology_text)},
            true,
            true
        )
        ON CONFLICT DO NOTHING;
    """)


def downgrade():
    op.drop_constraint('fk_voy_override_run_item', 'voy_override', type_='foreignkey')
    op.drop_index('idx_voy_override_created_at', table_name='voy_override')
    op.drop_index('idx_voy_override_run_item_id', table_name='voy_override')
    op.drop_table('voy_override')
    op.drop_table('voy_methodology')
