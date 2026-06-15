from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseAdapter


class FTBQuestsAdapter(BaseAdapter):
    """First official QLF adapter: FTB Quests native quest lang.

    The current CLI implementation still calls the legacy functions in qlf.py
    for extract/inject compatibility. This adapter defines the SDK boundary and
    source metadata that future adapters should follow.
    """

    name = "ftbquests"
    version = 1
    description = "FTB Quests native lang source under config/ftbquests/quests/lang"
    source_scope = "quest-only: config/ftbquests"
    capabilities = ["detect", "extract", "inject", "validate", "direct-write", "package"]

    def detect(self, instance_path: str | Path) -> dict[str, Any]:
        p = Path(instance_path).expanduser()
        if (p / "config" / "ftbquests").exists():
            ftb = p / "config" / "ftbquests"
        elif p.name.lower() == "ftbquests":
            ftb = p
        elif p.name.lower() == "quests":
            ftb = p.parent
        elif p.name.lower() == "config" and (p / "ftbquests").exists():
            ftb = p / "ftbquests"
        else:
            ftb = p

        quests = ftb / "quests"
        if not quests.exists() and ftb.name.lower() == "quests":
            quests = ftb
            ftb = ftb.parent

        lang = quests / "lang" / "en_us.snbt"
        return {
            "detected": bool(ftb.exists() and quests.exists()),
            "ftbquests": str(ftb) if ftb.exists() else None,
            "quests": str(quests) if quests.exists() else None,
            "lang": str(lang) if lang.exists() else None,
            "adapter": self.name,
            "capabilities": list(self.capabilities),
            "source_scope": self.source_scope,
        }

    def extract(self, instance_path: str | Path, locale: str = "en_us"):
        raise NotImplementedError("FTBQuestsAdapter.extract is still provided by legacy qlf.py in v1.9.x")

    def inject(self, *args: Any, **kwargs: Any):
        raise NotImplementedError("FTBQuestsAdapter.inject is still provided by legacy qlf.py in v1.9.x")
