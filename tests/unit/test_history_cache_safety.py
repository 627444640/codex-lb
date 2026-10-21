from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.fixtures.history_cache_safety import discard_test_history_cache

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm", "-journal"])
def test_foreign_cache_is_rejected_before_close_or_delete(tmp_path: Path, suffix: str) -> None:
    owned = tmp_path / "owned"
    owned.mkdir()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    path = foreign / "conversation_history.db"
    sentinel = path if not suffix else path.with_name(path.name + suffix)
    sentinel.write_bytes(b"synthetic-sentinel")
    close = Mock()

    with pytest.raises(RuntimeError, match="outside test-owned directories"):
        discard_test_history_cache(path, owned_roots=(owned,), close_cache=close)

    close.assert_not_called()
    assert sentinel.read_bytes() == b"synthetic-sentinel"


def test_owned_cache_and_sidecars_are_closed_then_removed(tmp_path: Path) -> None:
    path = tmp_path / "conversation_history.db"
    files = [path, *(path.with_name(path.name + suffix) for suffix in ("-wal", "-shm", "-journal"))]
    for candidate in files:
        candidate.write_bytes(b"synthetic-cache")

    def close() -> None:
        assert all(candidate.exists() for candidate in files)

    close_mock = Mock(side_effect=close)
    discard_test_history_cache(path, owned_roots=(tmp_path,), close_cache=close_mock)

    close_mock.assert_called_once()
    assert not any(candidate.exists() for candidate in files)


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm", "-journal"])
def test_symlinked_cache_or_sidecar_is_rejected_before_close(tmp_path: Path, suffix: str) -> None:
    owned = tmp_path / "owned"
    owned.mkdir()
    path = owned / "conversation_history.db"
    foreign = tmp_path / "outside.db"
    foreign.write_bytes(b"synthetic-sentinel")
    target = path if not suffix else path.with_name(path.name + suffix)
    target.symlink_to(foreign)
    close = Mock()

    with pytest.raises(RuntimeError, match="symlinks"):
        discard_test_history_cache(path, owned_roots=(owned,), close_cache=close)

    close.assert_not_called()
    assert foreign.read_bytes() == b"synthetic-sentinel"
    assert target.is_symlink()


def test_parent_symlink_escape_is_rejected_before_close(tmp_path: Path) -> None:
    owned = tmp_path / "owned"
    owned.mkdir()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    sentinel = foreign / "conversation_history.db"
    sentinel.write_bytes(b"synthetic-sentinel")
    (owned / "escape").symlink_to(foreign, target_is_directory=True)
    close = Mock()

    with pytest.raises(RuntimeError, match="outside test-owned directories"):
        discard_test_history_cache(owned / "escape" / sentinel.name, owned_roots=(owned,), close_cache=close)

    close.assert_not_called()
    assert sentinel.read_bytes() == b"synthetic-sentinel"


def test_cleanup_rechecks_target_after_close(tmp_path: Path) -> None:
    owned = tmp_path / "owned"
    owned.mkdir()
    path = owned / "conversation_history.db"
    foreign = tmp_path / "outside.db"
    foreign.write_bytes(b"synthetic-sentinel")

    def close() -> None:
        path.symlink_to(foreign)

    with pytest.raises(RuntimeError, match="changed after validation"):
        discard_test_history_cache(path, owned_roots=(owned,), close_cache=close)

    assert foreign.read_bytes() == b"synthetic-sentinel"
    assert path.is_symlink()


def test_default_data_dir_is_inside_test_database_root() -> None:
    from app.core.config.settings import get_settings

    settings = get_settings()
    root = Path(os.environ["CODEX_LB_DATA_DIR"]).resolve()
    assert settings.data_dir.resolve() == root
    assert root.name.startswith("codex-lb-tests-")
    assert root.is_dir()


def test_lazy_default_history_cache_uses_only_the_test_data_root() -> None:
    from app.modules.proxy.conversation_history import get_conversation_history_cache

    root = Path(os.environ["CODEX_LB_DATA_DIR"]).resolve()
    cache = get_conversation_history_cache()

    assert cache.path.resolve() == root / "conversation_history.db"
    assert cache.path.is_file()


def test_explicit_test_cache_remains_the_real_singleton(tmp_path: Path) -> None:
    from app.modules.proxy.conversation_history import (
        ConversationHistoryCache,
        get_conversation_history_cache,
        set_conversation_history_cache,
    )

    cache = ConversationHistoryCache(tmp_path / "explicit-history.db", enabled=False, start_maintenance=False)
    set_conversation_history_cache(cache)
    try:
        assert get_conversation_history_cache() is cache
        assert cache.path == tmp_path / "explicit-history.db"
    finally:
        set_conversation_history_cache(None)
