from __future__ import annotations

from typing import Any

from .ftbquests import FTBQuestsAdapter


def get_adapter_registry():
    """Return registered QLF source adapters.

    v1.9.1 registers only ftbquests. Future versions can add patchouli/kubejs
    by returning additional adapter instances here.
    """
    return {
        "ftbquests": FTBQuestsAdapter(),
    }


def adapter_info(adapter: Any) -> dict[str, Any]:
    """Return normalized adapter metadata for SDK/tooling commands."""
    if adapter is None:
        return {
            "name": "unknown",
            "version": 0,
            "description": "missing adapter object",
            "source_scope": "unknown",
            "capabilities": [],
            "sdk": "qlf-adapter-v1",
        }
    if hasattr(adapter, "info"):
        try:
            return adapter.info()
        except Exception as exc:  # defensive SDK reporting
            return {
                "name": getattr(adapter, "name", adapter.__class__.__name__),
                "version": getattr(adapter, "version", 0),
                "description": f"adapter info() failed: {exc}",
                "source_scope": getattr(adapter, "source_scope", "unknown"),
                "capabilities": list(getattr(adapter, "capabilities", [])),
                "sdk": "qlf-adapter-v1",
            }
    return {
        "name": getattr(adapter, "name", adapter.__class__.__name__),
        "version": getattr(adapter, "version", 0),
        "description": getattr(adapter, "description", ""),
        "source_scope": getattr(adapter, "source_scope", "unknown"),
        "capabilities": list(getattr(adapter, "capabilities", [])),
        "sdk": "qlf-adapter-v1",
    }
