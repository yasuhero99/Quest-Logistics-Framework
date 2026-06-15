from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SourceAdapter(Protocol):
    """QLF source adapter SDK interface.

    Adapter authors should implement this interface to plug a new quest-related
    source into QLF without changing the logistics core.

    Required metadata:
    - name: stable adapter id used in manifest entries, e.g. "ftbquests"
    - version: adapter API/version number
    - description: short human-readable description
    - source_scope: what this adapter is allowed to touch
    - capabilities: supported operations, e.g. detect/extract/inject/validate
    """

    name: str
    version: int
    description: str
    source_scope: str
    capabilities: list[str]

    def info(self) -> dict[str, Any]:
        ...

    def supports(self, capability: str) -> bool:
        ...

    def detect(self, instance_path: str | Path) -> dict[str, Any]:
        ...

    def extract(self, instance_path: str | Path, locale: str = "en_us") -> tuple[dict[str, Any], dict[str, Any]]:
        ...

    def inject(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        ...


class BaseAdapter:
    """Convenience base class for QLF adapters.

    Subclasses can override detect/extract/inject while inheriting standard
    metadata reporting used by `qlf adapters` and `qlf adapter-info`.
    """

    name = "base"
    version = 1
    description = "Base QLF source adapter"
    source_scope = "abstract"
    capabilities: list[str] = []

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "source_scope": self.source_scope,
            "capabilities": list(self.capabilities),
            "sdk": "qlf-adapter-v1",
        }

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def detect(self, instance_path: str | Path) -> dict[str, Any]:
        raise NotImplementedError

    def extract(self, instance_path: str | Path, locale: str = "en_us") -> tuple[dict[str, Any], dict[str, Any]]:
        raise NotImplementedError

    def inject(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError
