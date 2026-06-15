from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseAdapter


class ExampleAdapter(BaseAdapter):
    """Example QLF adapter template.

    Copy this file when creating a new adapter. Replace `example` with your
    source name, then register it in qlf_core/adapters/registry.py.

    This adapter is intentionally not registered by default.
    """

    name = "example"
    version = 1
    description = "Example adapter template for QLF source plugins"
    source_scope = "quest-only: describe what folders this adapter is allowed to touch"
    capabilities = ["detect"]

    def detect(self, instance_path: str | Path) -> dict[str, Any]:
        instance = Path(instance_path).expanduser()
        # Replace this with real detection logic.
        # Example: detect a folder under kubejs/assets or patchouli_books.
        return {
            "detected": False,
            "instance": str(instance),
            "adapter": self.name,
            "capabilities": list(self.capabilities),
            "source_scope": self.source_scope,
            "note": "This is a template adapter and is not meant to detect real files.",
        }

    def extract(self, instance_path: str | Path, locale: str = "en_us"):
        # Return (translation_data, manifest_fragment).
        # translation_data: {"some.key": "source text"}
        # manifest_fragment: same key -> source metadata used by inject/validate.
        raise NotImplementedError("Implement extract() for this adapter.")

    def inject(self, *args: Any, **kwargs: Any):
        # Write translated values back to this adapter's target files.
        raise NotImplementedError("Implement inject() for this adapter.")
