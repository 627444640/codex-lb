from __future__ import annotations

import pytest
from alembic import command
from anyio import to_thread
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.migrate import _build_alembic_config, check_schema_drift, run_upgrade

pytestmark = pytest.mark.integration
PARENT = "20260816_000000_add_model_source_embeddings"
FIELDS = {"actual_model", "cache_write_tokens", "pricing_version"}


@pytest.mark.asyncio
async def test_pricing_migration_preserves_history_upgrade_downgrade(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'pricing-migration.db'}"
    await to_thread.run_sync(lambda: run_upgrade(url, PARENT, bootstrap_legacy=False))
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO request_logs (request_id, model, status, input_tokens, output_tokens, cost_usd) "
                    "VALUES ('historic', 'gpt-5.6-sol', 'success', 100, 20, 0.123456789)"
                )
            )
        await to_thread.run_sync(lambda: run_upgrade(url, "head", bootstrap_legacy=False))
        assert await to_thread.run_sync(lambda: check_schema_drift(url)) == ()
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT input_tokens, output_tokens, cost_usd, actual_model, "
                        "cache_write_tokens, pricing_version "
                        "FROM request_logs WHERE request_id = 'historic'"
                    )
                )
            ).one()
            assert tuple(row) == (100, 20, 0.123456789, None, None, None)
        await to_thread.run_sync(lambda: command.downgrade(_build_alembic_config(url), PARENT))
        async with engine.begin() as connection:
            columns = await connection.run_sync(
                lambda conn: {c["name"] for c in inspect(conn).get_columns("request_logs")}
            )
            assert not columns & FIELDS
            # Partially present schema still completes the guarded upgrade.
            await connection.execute(text("ALTER TABLE request_logs ADD COLUMN actual_model VARCHAR"))
        await to_thread.run_sync(lambda: run_upgrade(url, "head", bootstrap_legacy=False))
        assert await to_thread.run_sync(lambda: check_schema_drift(url)) == ()
        async with engine.connect() as connection:
            assert (await connection.execute(text("SELECT cost_usd FROM request_logs"))).scalar_one() == 0.123456789
    finally:
        await engine.dispose()
