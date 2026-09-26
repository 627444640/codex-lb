from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command

import app.db.migrate as migrate_module
from app.db.alembic.revision_ids import OLD_TO_NEW_REVISION_MAP
from app.db.migrate import MigrationBootstrapError, _build_alembic_config, inspect_migration_state, run_upgrade

pytestmark = pytest.mark.integration

COST_REVISION = "20260325_000000_add_request_log_cost"
COST_PARENT = "20260321_210000_merge_request_log_tiers_and_dashboard_index_heads"


def _url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


def _prepare_old_database(path: Path, amount: float | None) -> str:
    url = _url(path)
    run_upgrade(url, COST_PARENT, bootstrap_legacy=False)
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE request_logs ADD COLUMN cost_usd FLOAT")
        connection.execute(
            "INSERT INTO request_logs (request_id, model, status, input_tokens, output_tokens, cost_usd) "
            "VALUES ('synthetic-history', 'gpt-5.4', 'success', 123, 45, ?)",
            (amount,),
        )
    return url


def _dump(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return "\n".join(connection.iterdump())


def test_raw_historical_migration_reproduces_the_overwrite_in_a_disposable_database(tmp_path: Path) -> None:
    path = tmp_path / "unsafe-control.sqlite"
    url = _prepare_old_database(path, 0.123456789)

    # Explicit control: bypass only the new runner guard on this throwaway
    # synthetic DB to establish why the immutable old migration is unsafe.
    command.upgrade(_build_alembic_config(url), COST_REVISION)

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT cost_usd, input_tokens, output_tokens FROM request_logs WHERE request_id='synthetic-history'"
        ).fetchone()
    assert row == (None, 123, 45)
    assert inspect_migration_state(url).current_revision == COST_REVISION


@pytest.mark.parametrize("target", ["head", COST_REVISION, "+1"])
@pytest.mark.parametrize("amount", [0.0, 0.123456789])
def test_runner_refuses_cost_backfill_before_any_schema_data_or_revision_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, amount: float
) -> None:
    path = tmp_path / "guarded.sqlite"
    url = _prepare_old_database(path, amount)
    before = _dump(path)

    def forbidden_write(*args, **kwargs):
        raise AssertionError("no bootstrap, version-capacity, remap or migration writes may precede the guard")

    monkeypatch.setattr(migrate_module, "_bootstrap_legacy_history", forbidden_write)
    monkeypatch.setattr(migrate_module, "_ensure_alembic_version_table_capacity", forbidden_write)
    monkeypatch.setattr(migrate_module, "_remap_legacy_alembic_revisions", forbidden_write)
    monkeypatch.setattr(migrate_module.command, "upgrade", forbidden_write)
    with pytest.raises(MigrationBootstrapError, match="Refusing upgrade through 20260325.*historical amounts"):
        run_upgrade(url, target, bootstrap_legacy=True)

    assert _dump(path) == before
    assert inspect_migration_state(url).current_revision == COST_PARENT


def test_runner_refuses_before_remapping_a_legacy_revision(tmp_path: Path) -> None:
    path = tmp_path / "legacy-revision.sqlite"
    url = _prepare_old_database(path, 4.25)
    legacy_revision = "010_add_idx_logs_requested_at"
    assert legacy_revision in OLD_TO_NEW_REVISION_MAP
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE alembic_version SET version_num=?", (legacy_revision,))
    before = _dump(path)

    with pytest.raises(MigrationBootstrapError, match="Refusing upgrade through"):
        run_upgrade(url, "head", bootstrap_legacy=True)

    assert _dump(path) == before
    assert inspect_migration_state(url).current_revision == legacy_revision


def test_runner_refuses_before_bootstrapping_legacy_history(tmp_path: Path) -> None:
    path = tmp_path / "legacy-bootstrap.sqlite"
    url = _prepare_old_database(path, 4.25)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE alembic_version")
        connection.execute("CREATE TABLE schema_migrations (name TEXT PRIMARY KEY)")
        connection.execute(
            "INSERT INTO schema_migrations(name) VALUES (?)", (migrate_module.LEGACY_MIGRATION_ORDER[0],)
        )
    before = _dump(path)

    with pytest.raises(MigrationBootstrapError, match="Refusing upgrade through"):
        run_upgrade(url, "head", bootstrap_legacy=True)

    assert _dump(path) == before
    assert inspect_migration_state(url).has_alembic_version_table is False


def test_upgrade_to_a_target_before_the_cost_backfill_preserves_existing_amounts(tmp_path: Path) -> None:
    path = tmp_path / "safe-target.sqlite"
    url = _prepare_old_database(path, 0.25)
    before = _dump(path)

    result = run_upgrade(url, COST_PARENT, bootstrap_legacy=False)

    assert result.current_revision == COST_PARENT
    assert _dump(path) == before


def test_existing_null_costs_can_upgrade_without_erasing_token_evidence(tmp_path: Path) -> None:
    path = tmp_path / "null-cost.sqlite"
    url = _prepare_old_database(path, None)

    result = run_upgrade(url, "head", bootstrap_legacy=False)

    assert result.current_revision == inspect_migration_state(url).head_revision
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT cost_usd, input_tokens, output_tokens FROM request_logs WHERE request_id='synthetic-history'"
        ).fetchone() == (None, 123, 45)


def test_fresh_install_and_current_head_startup_remain_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "fresh.sqlite"
    url = _url(path)
    result = run_upgrade(url, "head", bootstrap_legacy=False)
    assert result.current_revision == inspect_migration_state(url).head_revision
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO request_logs (request_id, model, status, input_tokens, output_tokens, cost_usd) "
            "VALUES ('synthetic-head-history', 'old-model', 'success', 123, 45, 0.135)"
        )
    before = _dump(path)

    def unexpected_upgrade(*args, **kwargs):
        raise AssertionError("current-head startup must continue to skip all migration work")

    monkeypatch.setattr(migrate_module.command, "upgrade", unexpected_upgrade)
    repeated = run_upgrade(url, "head", bootstrap_legacy=True)
    assert repeated.current_revision == result.current_revision
    assert _dump(path) == before
