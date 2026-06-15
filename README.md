# Quest Logistics Framework (QLF)

**Quest Logistics Framework** — 任務物流。

QLF extracts quest-related text, lets you translate it externally, validates the translated file, and injects it back to the correct source location.

QLF does **not** translate text by itself.

It handles logistics:

```text
Read → Merge → Validate → Deliver
```

## Current status

Core workflow is working for FTB Quests native lang files:

```text
FTB Quests
↓
resolve-text
↓
en_us.json + manifest.json
↓
external translation
↓
validate / diff / debug
↓
inject
↓
localized quest file
↓
Minecraft reads it
```

## Important non-goal

QLF is quest-focused.

It does not scan `mods/*.jar` or general mod language files. Item names, block names, entity names, and general mod translations belong to a future MLF-style workflow, not QLF.

## Quick start

Extract:

```powershell
python qlf.py resolve-text "<modpack instance>" --out en_us.json --manifest manifest.json --report resolve_report.json
```

Validate translated file:

```powershell
python qlf.py validate --manifest manifest.json --target zh_tw.json --report validate_report.json
```

Direct-write inject:

```powershell
python qlf.py inject --translation zh_tw.json --manifest manifest.json --locale zh_tw --write-to-instance "<modpack instance>" --report inject_report.json
```

Package mode:

```powershell
python qlf.py inject --translation zh_tw.json --manifest manifest.json --locale zh_tw --out-dir qlf_package --report inject_report.json
```

## Adapter SDK

QLF v1.9+ introduces an adapter system. FTB Quests is now the first official adapter.

List adapters:

```powershell
python qlf.py adapters
```

Adapter info:

```powershell
python qlf.py adapter-info ftbquests
```

Detect sources:

```powershell
python qlf.py sources --instance "<modpack instance>"
```

## Documentation

See:

- `docs/QUICKSTART.md`
- `docs/ARCHITECTURE.md`
- `docs/SDK.md`
- `docs/MANIFEST.md`
- `docs/SCOPE.md`
- `docs/ROADMAP.md`

## Safety

QLF only reads and writes local files.

It does not require:

- Minecraft runtime
- Launcher-specific support
- Localizer mod
- AI API key
- Internet access

When direct-write inject overwrites an existing target file, QLF creates a `.bak` backup.

## v1.9.3 Adapter Developer Kit

This release adds adapter examples and a template generator:

```powershell
python qlf.py adapter-template patchouli --out qlf_core\adapters\patchouli.py
```

New docs:

- `docs/SDK_EXAMPLE.md`
- `docs/ADAPTER_TEMPLATE.md`
- `templates/adapter_template.py`
- `qlf_core/adapters/example_adapter.py`

These files are for adapter development only. The example adapter is not registered by default.
