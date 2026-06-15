# QLF Architecture

QLF means **Quest Logistics Framework**. It is a quest-text logistics tool, not a translator.

Its job is:

```text
quest sources
  ↓
extract
  ↓
translation JSON
  ↓
external translation by human / AI
  ↓
validate
  ↓
inject
  ↓
original quest source locations
```

## Core idea

QLF is built around a logistics pipeline:

1. **Extract** text from supported quest-related sources.
2. **Normalize** text into one translation file.
3. **Track** where every key came from using `manifest.json`.
4. **Validate** the translated file before writing anything.
5. **Inject** translated text back to the correct source location.

This is the `Many Sources → One Translation File → Many Sources` model.

## Project boundary

QLF is quest-focused.

QLF should handle:

- FTB Quests text
- Quest/chapter/task/reward text
- Pack-authored quest guide text in the future
- Quest-related KubeJS or Patchouli sources in the future, if they are pack-authored

QLF should **not** handle:

- `mods/*.jar`
- General mod language files
- Item names
- Block names
- Entity names
- JEI/tooltips unrelated to quests

Those belong to a future MLF-style workflow, not QLF.

## Current components

```text
qlf.py
  CLI entry point

qlf_core/
  adapters/
    base.py       Adapter SDK interface
    ftbquests.py  First official adapter
    registry.py   Adapter registry
```

The current code still keeps much of the legacy logistics implementation inside `qlf.py`, but v1.9+ begins the adapter refactor so source support can grow without rewriting the core workflow.

## Adapter model

Each supported source is represented by an adapter.

Current adapter:

```text
ftbquests
```

Future adapters may include:

```text
patchouli
quest_kubejs
```

The core should not know source-specific details. It should ask adapters to detect, extract, and inject source-specific content.

## Manifest role

`manifest.json` is the logistics map.

It records:

- source system version
- source files
- source adapter name
- key metadata
- value type
- line count
- original relative path

The manifest lets QLF know where every translation key must go during inject.

Without the manifest, QLF can extract text but cannot safely return it to its original source.
