"""Close and remove only history caches owned by this test run."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

_SQLITE_SUFFIXES = ("", "-wal", "-shm", "-journal")


def discard_test_history_cache(
    path: Path,
    *,
    owned_roots: tuple[Path, ...],
    close_cache: Callable[[], None],
) -> None:
    """Validate every target before close, which can itself flush SQLite data."""
    roots = tuple(root.resolve() for root in owned_roots)
    candidates = tuple(path if not suffix else path.with_name(path.name + suffix) for suffix in _SQLITE_SUFFIXES)
    resolved_targets: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if candidate.is_symlink() or not any(resolved != root and resolved.is_relative_to(root) for root in roots):
            raise RuntimeError("Refusing to clean a history cache outside test-owned directories or through symlinks")
        resolved_targets.append(resolved)

    close_cache()
    for candidate, resolved in zip(candidates, resolved_targets, strict=True):
        # Closing may flush/create sidecars; revalidate before each removal.
        if candidate.is_symlink() or candidate.resolve() != resolved:
            raise RuntimeError("History cache cleanup target changed after validation")
        candidate.unlink(missing_ok=True)
