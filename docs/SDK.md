# QLF Adapter SDK

The adapter SDK defines how new quest-related sources plug into QLF.

SDK id:

```text
qlf-adapter-v1
```

## Adapter metadata

Every adapter should expose:

```python
name: str
version: int
description: str
source_scope: str
capabilities: list[str]
```

Example:

```python
name = "ftbquests"
version = 1
description = "FTB Quests native lang source under config/ftbquests/quests/lang"
source_scope = "quest-only: config/ftbquests"
capabilities = ["detect", "extract", "inject", "validate", "direct-write", "package"]
```

## Required methods

Adapters should implement or inherit:

```python
def info(self) -> dict:
    ...

def supports(self, capability: str) -> bool:
    ...

def detect(self, instance_path) -> dict:
    ...

def extract(self, instance_path, locale="en_us") -> tuple[dict, dict]:
    ...

def inject(self, *args, **kwargs) -> dict:
    ...
```

## Capabilities

Recommended capability names:

```text
detect
extract
inject
validate
direct-write
package
```

An adapter does not need to support every capability. For example, a future read-only source may support only:

```text
detect
extract
```

## Source scope

`source_scope` describes what the adapter is allowed to touch.

Good examples:

```text
quest-only: config/ftbquests
quest-only: pack-authored patchouli books
quest-only: kubejs quest text
```

Bad examples:

```text
all mod lang files
all json files
all kubejs files
```

QLF must stay quest-focused.

## Manifest requirements

Every extracted key should include enough metadata for validation and inject.

Recommended key entry:

```json
{
  "source": "ftbquests",
  "adapter": "ftbquests",
  "source_id": 0,
  "value_type": "string",
  "line_count": 1
}
```

The adapter name must be stable because injected output depends on it.

## Testing a new adapter

A new adapter is not considered usable until it can pass:

```text
1. detect real test data
2. extract real text
3. produce manifest entries
4. validate translated file
5. inject/package output
6. confirm the target system reads the output
```

Do not add adapters without real test data.
