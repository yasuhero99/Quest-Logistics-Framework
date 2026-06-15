# QLF Adapter SDK Example

QLF adapters are small source modules that teach the logistics core how to detect, extract, validate, and inject one quest-related source.

The important rule is scope:

- QLF adapters should handle quest-related content.
- QLF adapters should not extract general mod language files, item names, block names, or `mods/*.jar` contents.

## Minimal adapter

```python
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
```

## Registering an adapter

Open `qlf_core/adapters/registry.py` and add your adapter:

```python
from .ftbquests import FTBQuestsAdapter
from .myadapter import MyAdapter


def get_adapter_registry():
    return {
        "ftbquests": FTBQuestsAdapter(),
        "myadapter": MyAdapter(),
    }
```

Then test:

```powershell
python qlf.py adapters
python qlf.py adapter-info myadapter
python qlf.py sources --instance "C:\Path\To\Modpack"
```

## Capabilities

Capabilities describe what the adapter can currently do.

Common values:

- `detect`: can detect whether the source exists in an instance.
- `extract`: can extract source text into the QLF translation JSON.
- `inject`: can write translated content back.
- `validate`: can validate target values for this source.
- `direct-write`: can write directly into an instance folder.
- `package`: can create a package folder instead of writing directly.

An adapter can start with only `detect` and grow later.

## Manifest requirements

When an adapter extracts text, every key should have manifest metadata:

```json
{
  "myadapter.some.key": {
    "source": "myadapter",
    "adapter": "myadapter",
    "source_id": 1,
    "source_file": "...",
    "relative_path": "...",
    "value_type": "string",
    "line_count": 1
  }
}
```

The manifest is the logistics slip. Inject uses it to deliver translated values back to the right source.
