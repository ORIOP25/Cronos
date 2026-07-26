# Ficheiro: backend/alembic/env.py
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# 1. Adicionar o projeto ao path para importar a App
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 2. Configuração do URL Real (Database)
from app.config import settings

config = context.config
if settings.MIGRATION_DATABASE_URL is None:
    raise RuntimeError("MIGRATION_DATABASE_URL is required for Alembic")
config.set_main_option("sqlalchemy.url", str(settings.MIGRATION_DATABASE_URL))

# Configurar Logs
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 4. IMPORTS DOS MODELOS (O Passo Mágico)
# Importamos a Base E os modelos.
# Mesmo que o editor diga "unused import", ISTO É OBRIGATÓRIO.
# Ao importar 'app.models', todas as classes (User, Teacher, etc.)
# registam-se automaticamente na 'Base'.
from app.models import Base  # noqa: E402

# Definir o alvo para o Alembic olhar
target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):
    """Ignore migration-only native tenant constraints during drift checks."""
    if (
        reflected
        and compare_to is None
        and type_
        in {
            "foreign_key_constraint",
            "unique_constraint",
        }
    ):
        return not ((name or "").endswith("_org") or (name or "").endswith("_org_id"))
    return True


def run_migrations_offline() -> None:
    """Modo Offline (Gera SQL sem ligar à BD)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Modo Online (Liga à BD e aplica mudanças)."""

    # O engine_from_config vai ler o "sqlalchemy.url" que definimos lá em cima
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
