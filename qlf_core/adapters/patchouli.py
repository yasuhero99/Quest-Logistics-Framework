from __future__ import annotations

from pathlib import Path
from typing import Any

from qlf_core.adapters.base import BaseAdapter


class PatchouliAdapter(BaseAdapter):
    name = "patchouli"
    version = 1
    description = "TODO: describe this quest-related source"
    source_scope = "quest-only: TODO describe allowed folders"
    capabilities = ["detect"]

    def detect(self, instance_path: str | Path) -> dict[str, Any]:
        instance = Path(instance_path).expanduser()
        # TODO: replace with real detection logic.
        return {
            "detected": False,
            "instance": str(instance),
            "adapter": self.name,
            "capabilities": list(self.capabilities),
            "source_scope": self.source_scope,
        }

    def extract(self, instance_path: str | Path, locale: str = "en_us"):
        # TODO: return (translation_data, manifest_fragment).
        raise NotImplementedError

    def inject(self, *args: Any, **kwargs: Any):
        # TODO: write translated values back to this source.
        raise NotImplementedError
