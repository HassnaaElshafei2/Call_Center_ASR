from alembic import context
from sqlalchemy import engine_from_config, pool

from callintel import models  # noqa: F401  (registers the tables)
from callintel.config import settings
from callintel.db import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
