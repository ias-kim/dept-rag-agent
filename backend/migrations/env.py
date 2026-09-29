from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings

url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_url
connectable = engine_from_config({"sqlalchemy.url": url}, prefix="sqlalchemy.", poolclass=pool.NullPool)

with connectable.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
