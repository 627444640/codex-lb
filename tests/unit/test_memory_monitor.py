from __future__ import annotations

import builtins
import ctypes
import importlib
import mmap
import sys
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.types import ASGIApp

from app.core.resilience.bulkhead import BulkheadMiddleware, BulkheadSemaphore

pytestmark = pytest.mark.unit


def test_get_rss_bytes_returns_positive_number():
    from app.core.resilience import memory_monitor

    rss = memory_monitor.get_rss_bytes()
    assert isinstance(rss, int)
    assert rss > 0


def test_is_memory_pressure_returns_false_when_threshold_disabled():
    from app.core.resilience import memory_monitor

    memory_monitor.configure(reject_threshold_mb=0)
    assert memory_monitor.is_memory_pressure() is False
    assert memory_monitor.is_memory_warning() is False


def test_memory_warning_threshold_is_derived_at_80_percent_of_reject(monkeypatch):
    from app.core.resilience import memory_monitor

    memory_monitor.configure(reject_threshold_mb=100)
    try:
        reject_bytes = 100 * 1024 * 1024
        warning_bytes = int(reject_bytes * 0.8)
        monkeypatch.setattr(memory_monitor, "get_rss_bytes", lambda: warning_bytes - 1)
        assert memory_monitor.is_memory_warning() is False
        assert memory_monitor.is_memory_pressure() is False
        monkeypatch.setattr(memory_monitor, "get_rss_bytes", lambda: warning_bytes)
        assert memory_monitor.is_memory_warning() is True
        assert memory_monitor.is_memory_pressure() is False
        monkeypatch.setattr(memory_monitor, "get_rss_bytes", lambda: reject_bytes)
        assert memory_monitor.is_memory_pressure() is True
    finally:
        memory_monitor.configure(reject_threshold_mb=0)


def test_memory_monitor_imports_on_windows_without_resource(monkeypatch: pytest.MonkeyPatch):
    module_name = "app.core.resilience.memory_monitor"
    package = importlib.import_module("app.core.resilience")
    original_module = sys.modules.get(module_name)
    sys.modules.pop(module_name, None)
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None):
        if name == "resource":
            raise ModuleNotFoundError("No module named 'resource'")
        return real_import_module(name, package)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    try:
        module = importlib.import_module(module_name)
        assert callable(module.get_rss_bytes)
    finally:
        sys.modules.pop(module_name, None)
        if original_module is not None:
            sys.modules[module_name] = original_module
            setattr(package, "memory_monitor", original_module)


def test_get_rss_bytes_returns_zero_when_no_provider_available(monkeypatch: pytest.MonkeyPatch):
    from app.core.resilience import memory_monitor

    real_import = builtins.__import__

    def fake_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
        if name == "psutil":
            raise ImportError("psutil unavailable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(memory_monitor, "_get_macos_rss_bytes", lambda: None)
    monkeypatch.setattr(memory_monitor, "_get_windows_rss_bytes", lambda: None)
    monkeypatch.setattr(memory_monitor, "_rss_provider_warning_logged", False)
    monkeypatch.setattr(memory_monitor.sys, "platform", "win32")

    assert memory_monitor.get_rss_bytes() == 0


@pytest.mark.parametrize("result,returned_count", [(5, 12), (0, 1)])
def test_macos_provider_rejects_failed_or_incomplete_task_info(
    monkeypatch: pytest.MonkeyPatch, result: int, returned_count: int
) -> None:
    from app.core.resilience import memory_monitor

    def task_info(task: int, flavor: int, info: object, count: ctypes.c_void_p) -> int:
        del task, flavor, info
        ctypes.cast(count, ctypes.POINTER(ctypes.c_uint)).contents.value = returned_count
        return result

    library = SimpleNamespace(mach_task_self=lambda: 1, task_info=task_info)
    monkeypatch.setattr(memory_monitor.sys, "platform", "darwin")
    monkeypatch.setattr(memory_monitor, "_macos_task_library", lambda: library)
    assert memory_monitor._get_macos_rss_bytes() is None


@pytest.mark.skipif(sys.platform != "darwin", reason="Exercises the native macOS current-RSS provider")
async def test_macos_admission_recovers_after_native_memory_is_released(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.resilience import memory_monitor

    real_import = builtins.__import__

    def without_psutil(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
        if name == "psutil":
            raise ImportError("Exercise the native fallback")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", without_psutil)
    app = FastAPI()

    @app.get("/v1/work")
    async def work() -> dict[str, bool]:
        return {"ok": True}

    guarded_app = BulkheadMiddleware(cast(ASGIApp, app), bulkhead=BulkheadSemaphore())
    baseline = memory_monitor.get_rss_bytes()
    assert baseline > 0
    memory_monitor.configure(reject_threshold_mb=baseline // (1024 * 1024) + 24)
    try:
        async with AsyncClient(transport=ASGITransport(app=guarded_app), base_url="http://testserver") as client:
            assert (await client.get("/v1/work")).status_code == 200
            with mmap.mmap(-1, 64 * 1024 * 1024) as allocation:
                for offset in range(0, len(allocation), mmap.PAGESIZE):
                    allocation[offset] = 1
                overloaded = await client.get("/v1/work")
                assert overloaded.status_code == 503
                assert overloaded.json()["error"]["code"] == "proxy_unavailable"
            recovered = await client.get("/v1/work")
            assert recovered.status_code == 200
            assert recovered.json() == {"ok": True}
    finally:
        memory_monitor.configure(reject_threshold_mb=0)
