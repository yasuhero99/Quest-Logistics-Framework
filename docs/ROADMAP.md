# QLF Roadmap

## Completed milestones

### v1.5 — Inject MVP

- Generate manifest
- Inject translated JSON/SNBT using manifest
- Produce native `zh_tw.snbt`

### v1.6 — Direct Write

- Write directly into a modpack instance
- Create `.bak` backups before overwrite

### v1.7 — Debug and Diff

- `debug` command
- `diff` command
- Dry-run style inspection before writing

### v1.8 — Validation System

- Missing key check
- Extra key check
- Empty value warning
- Duplicate key check
- Type mismatch check

### v1.8.1 — Manifest Type System

- Manifest records `value_type`
- Manifest records `line_count`
- Validate no longer falsely reports quest description list/string mismatches

### v1.9 — Adapter Skeleton

- Adapter registry
- `sources` command
- FTB Quests becomes the first adapter
- Manifest v3 includes adapter source data

### v1.9.1 — Adapter SDK

- `adapters` command
- `adapter-info` command
- Adapter metadata
- Adapter capabilities
- Adapter source scope

## Next recommended milestones

### v1.9.2 — Documentation Release

- Architecture docs
- SDK docs
- Manifest docs
- Scope/non-goal docs

### v1.9.3 — Adapter developer utilities

Possible ideas:

- `adapter-template <name>`
- adapter self-check
- adapter capability validation

### v2.0 — First non-FTBQ adapter

Only start this when real test data exists.

Candidates:

- Pack-authored Patchouli quest/guide books
- Quest-related KubeJS text

Do not implement adapters based only on guessed formats.

### Future — GUI

GUI should wrap the existing stable workflow:

```text
select instance
extract
validate
inject
```

GUI should come after the core workflow and adapter model are stable.
