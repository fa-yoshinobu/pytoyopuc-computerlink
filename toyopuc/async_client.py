from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import Any

from .client import ToyopucClient
from .high_level import ToyopucDeviceClient


async def _run_sync_in_worker(func: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    try:
        to_thread = asyncio.to_thread
    except AttributeError:
        loop = asyncio.get_running_loop()
        call = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, call)
    return await to_thread(func, *args, **kwargs)


def _install_async_wrapper(async_cls: type, method_name: str) -> None:
    async def _async_method(self: Any, *args: Any, **kwargs: Any) -> Any:
        bound = getattr(self._client, method_name)
        return await _run_sync_in_worker(bound, *args, **kwargs)

    _async_method.__name__ = method_name
    _async_method.__qualname__ = f"{async_cls.__name__}.{method_name}"
    setattr(async_cls, method_name, _async_method)


class _AsyncToyopucClientBase:
    _sync_client_cls = ToyopucClient

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        object.__setattr__(self, "_client", self._sync_client_cls(*args, **kwargs))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_client" or hasattr(type(self), name):
            object.__setattr__(self, name, value)
            return
        setattr(self._client, name, value)

    async def __aenter__(self) -> _AsyncToyopucClientBase:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()


class AsyncToyopucClient(_AsyncToyopucClientBase):
    """Async wrapper for the low-level TOYOPUC client."""

    _sync_client_cls = ToyopucClient


class AsyncToyopucDeviceClient(_AsyncToyopucClientBase):
    """Async wrapper for the high-level TOYOPUC client."""

    _sync_client_cls = ToyopucDeviceClient


_CLIENT_ASYNC_METHODS = [
    "connect",
    "close",
    "send_raw",
    "send_payload",
    "read_words",
    "write_words",
    "read_bytes",
    "write_bytes",
    "read_bit",
    "write_bit",
    "read_dword",
    "write_dword",
    "read_dwords",
    "write_dwords",
    "read_float32",
    "write_float32",
    "read_float32s",
    "write_float32s",
    "read_words_multi",
    "write_words_multi",
    "read_bytes_multi",
    "write_bytes_multi",
    "read_ext_words",
    "write_ext_words",
    "read_ext_bytes",
    "write_ext_bytes",
    "read_ext_multi",
    "write_ext_multi",
    "pc10_block_read",
    "pc10_block_write",
    "pc10_multi_read",
    "pc10_multi_write",
    "read_fr_words",
    "write_fr_words",
    "write_fr_words_ex",
    "commit_fr_block",
    "commit_fr_range",
    "write_fr_words_committed",
    "fr_register",
    "relay_command",
    "relay_nested",
    "send_via_relay",
    "relay_read_words",
    "relay_write_words",
    "relay_read_clock",
    "relay_write_clock",
    "relay_read_cpu_status",
    "relay_read_cpu_status_a0_raw",
    "relay_read_cpu_status_a0",
    "relay_write_fr_words",
    "relay_write_fr_words_ex",
    "relay_fr_register",
    "relay_commit_fr_block",
    "relay_commit_fr_range",
    "relay_wait_fr_write_complete",
    "read_clock",
    "read_cpu_status",
    "read_cpu_status_a0_raw",
    "read_cpu_status_a0",
    "wait_fr_write_complete",
    "write_clock",
]

_HIGH_LEVEL_ASYNC_METHODS = [
    "resolve_device",
    "relay_read",
    "relay_write",
    "relay_read_words",
    "relay_write_words",
    "relay_read_many",
    "relay_write_many",
    "read_fr",
    "relay_read_fr",
    "write_fr",
    "relay_write_fr",
    "commit_fr",
    "relay_commit_fr",
    "read",
    "write",
    "read_many",
    "write_many",
    "read_dword",
    "write_dword",
    "read_dwords",
    "write_dwords",
    "read_float32",
    "write_float32",
    "read_float32s",
    "write_float32s",
    "relay_read_dword",
    "relay_write_dword",
    "relay_read_dwords",
    "relay_write_dwords",
    "relay_read_float32",
    "relay_write_float32",
    "relay_read_float32s",
    "relay_write_float32s",
]

for _method_name in _CLIENT_ASYNC_METHODS:
    _install_async_wrapper(AsyncToyopucClient, _method_name)
    _install_async_wrapper(AsyncToyopucDeviceClient, _method_name)

for _method_name in _HIGH_LEVEL_ASYNC_METHODS:
    _install_async_wrapper(AsyncToyopucDeviceClient, _method_name)
