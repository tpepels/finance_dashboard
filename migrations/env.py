"""Apply ordered database schema migrations; DATABASE_URL is mandatory."""
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from finance_dashboard.database import Base, database_url
from finance_dashboard import database as _models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(
        url=database_url(), target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    settings = config.get_section(config.config_ini_section) or {}
    settings["sqlalchemy.url"] = database_url()
    engine = engine_from_config(settings, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
