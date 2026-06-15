# QLF Quick Start

## 1. Extract source text

```powershell
python qlf.py resolve-text "<modpack instance>" --out en_us.json --manifest manifest.json --report resolve_report.json
```

## 2. Translate

Copy:

```text
en_us.json
```

to:

```text
zh_tw.json
```

Translate only the values. Do not edit keys.

Correct:

```json
"quest.123.title": "機械動力"
```

Wrong:

```json
"quest.123.title.tw": "機械動力"
```

## 3. Validate

```powershell
python qlf.py validate --manifest manifest.json --target zh_tw.json --report validate_report.json
```

If `ok` is true, continue.

## 4. Debug output path

```powershell
python qlf.py debug --instance "<modpack instance>" --manifest manifest.json --translation zh_tw.json --locale zh_tw --write-to-instance "<modpack instance>" --report debug_report.json
```

## 5. Inject directly

```powershell
python qlf.py inject --translation zh_tw.json --manifest manifest.json --locale zh_tw --write-to-instance "<modpack instance>" --report inject_report.json
```

QLF creates backups before overwriting existing target files.

## 6. Package mode instead of direct write

```powershell
python qlf.py inject --translation zh_tw.json --manifest manifest.json --locale zh_tw --out-dir qlf_package --report inject_report.json
```

Then copy the generated package contents into the modpack root.
