"""The Fyers streaming SDK, imported with the one shim it needs.

``FyersWebsocket/data_ws.py`` opens with ``from pkg_resources import
resource_filename``, and setuptools removed ``pkg_resources`` in 81 — so on a
current setuptools the SDK raises ``ModuleNotFoundError`` at import, before any
of our code runs. ``override-dependencies`` in ``pyproject.toml`` deliberately
holds setuptools at ``>=84.1.0`` to keep four advisories out of the image, and
``fyers-apiv3`` pins ``setuptools==68.0.0`` precisely because of this import.
The two requirements are in direct conflict.

Three ways to settle it, and why this is the third:

**Pin setuptools back.** Re-admits PYSEC-2025-49, PYSEC-2026-1918,
PYSEC-2026-3447 and GHSA-xmj3-9gf7-h52w into the published image, which is
exactly what unpinning them set out to remove.

**Vendor the socket.** ``data_ws.py`` is 1812 lines, most of it parsing a
binary frame format we have no specification for. Owning that to avoid one
function call would be the most expensive possible fix, and every SDK upgrade
would become a merge.

**Supply the one function the SDK calls.** It uses ``resource_filename`` twice,
both times as ``resource_filename('fyers_apiv3.FyersWebsocket', 'map.json')`` —
locating a data file inside its own installed package. ``importlib.resources``
has been the stdlib answer to that since 3.9 and resolves the same path, so the
shim below is a rename rather than a reimplementation. It is ~25 lines, it goes
away by itself the day the SDK modernises its import, and it leaves setuptools
alone.

Everything above this module speaks to the SDK through ``data_socket.py``;
this exists only so that import cannot fail for a packaging reason. The shim is
installed *only* when ``pkg_resources`` is genuinely absent — where a real one
is present it is left untouched.
"""

from __future__ import annotations

import sys
import types
from importlib import resources
from typing import Any

from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


def resource_filename(package: str, resource: str) -> str:
    """``pkg_resources.resource_filename``, over ``importlib.resources``.

    Returns a filesystem path, which is what the caller does with it — the SDK
    passes the result straight to ``open()``. That assumes an unpacked package
    on disk, but so did ``resource_filename``, so the shim inherits the
    constraint rather than introducing it.
    """
    return str(resources.files(package) / resource)


def _install_shim() -> None:
    """Make ``import pkg_resources`` resolve, if nothing else provides it."""
    try:
        import pkg_resources  # noqa: F401, PLC0415
    except ModuleNotFoundError:
        shim = types.ModuleType("pkg_resources")
        shim.__doc__ = (
            "Minimal stand-in installed by chartnexus.infrastructure.brokers."
            "fyers.sdk — supplies only resource_filename, for the Fyers SDK."
        )
        shim.resource_filename = resource_filename  # type: ignore[attr-defined]
        sys.modules["pkg_resources"] = shim
        log.info("fyers_sdk_pkg_resources_shimmed")


def _load() -> Any:
    """The SDK's websocket module, shim first.

    Loaded through a function so the shim is guaranteed to be installed before
    the import runs. At module scope an import sorter would hoist the vendor
    import above the call and the ordering would silently break.
    """
    _install_shim()
    from fyers_apiv3.FyersWebsocket import data_ws  # noqa: PLC0415

    return data_ws


#: The SDK module. ``data_socket`` reaches the socket class through this.
data_ws: Any = _load()


__all__ = ["data_ws", "resource_filename"]
