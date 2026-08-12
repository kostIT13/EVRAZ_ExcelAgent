"""Remove app_readonly role and its privileges

Revision ID: f1a2b3c4d5e6
Revises: d9f2c3a1e5b7
Create Date: 2026-08-12 17:45:00.000000

Read-only роль ``app_readonly`` больше не используется: Executor-узел
подключается к БД под основной ролью ``user``. Безопасность SQL обеспечивается
keyword-blacklist валидацией в codegen_node.

Эта миграция отзывает выданные роли привилегии на схему ``mart`` и удаляет
роль ``app_readonly`` (если она существует), созданную ранее в b7a4f21e3c91.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'd9f2c3a1e5b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Отзываем default privileges для схемы mart, выданные app_readonly
    # (ALTER DEFAULT PRIVILEGES ... GRANT SELECT). Без этого DROP ROLE падает
    # с DependentObjectsStillExist. Операции условные, чтобы не падали, если
    # роли/привилегий уже нет.
    # user — зарезервированное слово, поэтому берём его в двойные кавычки.
    bind.execute(
        sa.text(
            "DO $$ BEGIN "
            " IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_readonly') THEN "
            "   EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE \"user\" IN SCHEMA mart "
            "            REVOKE SELECT ON TABLES FROM app_readonly'; "
            " END IF; "
            "END $$;"
        )
    )
    bind.execute(
        sa.text(
            "DO $$ BEGIN "
            " IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_readonly') THEN "
            "   EXECUTE 'REVOKE ALL PRIVILEGES ON SCHEMA mart FROM app_readonly'; "
            "   EXECUTE 'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA mart "
            "            FROM app_readonly'; "
            "   DROP ROLE app_readonly; "
            " END IF; "
            "END $$;"
        )
    )


def downgrade() -> None:
    # Роль больше не используется; повторное создание не требуется.
    pass