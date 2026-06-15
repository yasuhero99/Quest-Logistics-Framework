from __future__ import annotations

from pathlib import Path
from typing import Any

from qlf_core.adapters.base import BaseAdapter


class MyAdapter(BaseAdapter):
    name = "myadapter"
    version = 1
    description = "Describe this quest-related source"
    source_scope = "quest-only: describe allowed folders here"
    capabilities = ["detect"]

    def detect(self, instance_path: str | Path) -> dict[str, Any]:
        instance = Path(instance_path).expanduser()
        return {
            "detected": False,
            "instance": str(instance),
            "adapter": self.name,
            "capabilities": list(self.capabilities),
            "source_scope": self.source_scope,
        }

    def extract(self, instance_path: str | Path, locale: str = "en_us"):
        raise NotImplementedError

    def inject(self, *args: Any, **kwargs: Any):
        raise NotImplementedError
