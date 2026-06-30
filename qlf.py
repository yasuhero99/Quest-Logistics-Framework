#!/usr/bin/env python3
"""
QLF v1.9.3 - Quest Logistics Framework prototype with adapter SDK and examples

New in v0.8:
- More forgiving path handling:
  You may pass an instance folder, config/ftbquests, ftbquests/quests, or a lang file.
- Auto-detects two modes:
  1) lang mode: quests/lang/en_us.snbt exists. This is the normal/translatable mode.
  2) raw mode: no lang file exists. It scans raw .snbt files and reports candidate strings,
     but it does NOT keyify/patch raw quests yet.
- Adds `locate` command to show what QLF sees in a folder.
- Adds `export-raw` to export ftbquests translation-key templates from raw quest SNBT files.
- Adds `compare-raw` to compare raw keys with an existing Localizer/lang file.
- Fixes embedded ftbquests key extraction inside JSON rich text and hover arrays.
- Adds `merge-template` to fill a blank template with values from an existing lang/localizer file.
- Adds `diff-lang` to compare two lang files and report added/removed/changed keys.
- Adds `resolve-text` / `export-auto` multi-mode resolver:
  A) native quests/lang/en_us.snbt -> key + source text
  B) kubejs/assets/**/lang/en_us.json or resourcepack lang -> key + source text
  C) raw FTBQ keys -> blank fallback

Important:
Raw mode can now export blank translation templates from existing translation references,
but it still cannot keyify/patch raw human text yet.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict, Counter
from pathlib import Path
import shutil
from typing import Any

# v1.9 adapter skeleton. QLF still keeps compatibility with the single-file CLI,
# but source detection/registry is now externalized so future source adapters can plug in.
try:
    from qlf_core.adapters.registry import get_adapter_registry, adapter_info
except Exception:  # keep qlf.py runnable even if package files are missing
    get_adapter_registry = None
    adapter_info = None

RESOURCE_LOCATION_RE = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_/.-]+$")
HEX_ID_RE = re.compile(r"^[0-9A-Fa-f]{8,32}$")
NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?[dDfFlLsS]?$")
URL_RE = re.compile(r"^(https?://|www\.)", re.I)
FILELIKE_RE = re.compile(r"^[\w./\\-]+\.(png|jpg|jpeg|webp|json|snbt|txt|ogg|wav|mp3|nbt)$", re.I)
TRANSLATION_REF_RE = re.compile(r"^\{?[A-Za-z0-9_.:-]+\}?$")

RAW_SKIP_VALUES = {
    "item", "checkmark", "custom", "loot_table", "xp", "random", "choice", "table", "boss", "monster", "passive",
    "circle", "square", "diamond", "disabled", "linear", "default", "hide", "show", "true", "false", "empty",
    "create", "minecraft", "forge", "ftbquests", "kubejs", "kubjs", "chapter", "quest", "task", "reward",
}


def _strip_outer_braces(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text[1:-1]
    return text


def _unescape_snbt_string(s: str) -> str:
    return json.loads('"' + s + '"')


def _escape_snbt_string(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def parse_snbt_lang(text: str) -> OrderedDict[str, Any]:
    body = _strip_outer_braces(text)
    lines = body.splitlines()
    result: OrderedDict[str, Any] = OrderedDict()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        key = key.strip().strip('"')
        rest = rest.strip()
        if not key:
            continue
        if rest.startswith('"'):
            m = re.match(r'"((?:\\.|[^"\\])*)"\s*$', rest)
            if not m:
                raise ValueError(f"Cannot parse string value at line {i}: {raw}")
            result[key] = _unescape_snbt_string(m.group(1))
            continue
        if rest.startswith("["):
            acc = rest
            while not acc.rstrip().endswith("]"):
                if i >= len(lines):
                    raise ValueError(f"Unclosed array for key {key}")
                acc += "\n" + lines[i].strip()
                i += 1
            inner = acc.strip()[1:-1].strip()
            values: list[str] = []
            if inner:
                for m in re.finditer(r'"((?:\\.|[^"\\])*)"', inner):
                    values.append(_unescape_snbt_string(m.group(1)))
                leftover = re.sub(r'"(?:\\.|[^"\\])*"', '', inner).replace(',', '').strip()
                if leftover:
                    raise ValueError(f"Unsupported array content for key {key}: {leftover[:80]}")
            result[key] = values
            continue
        # Ignore simple non-string values in lang files just in case.
        continue
    return result


def dump_snbt_lang(data: dict[str, Any]) -> str:
    lines = ["{"]
    for key, value in data.items():
        if isinstance(value, list):
            if len(value) <= 1:
                inner = ", ".join(_escape_snbt_string(str(x)) for x in value)
                lines.append(f"\t{key}: [{inner}]")
            else:
                lines.append(f"\t{key}: [")
                for item in value:
                    lines.append(f"\t\t{_escape_snbt_string(str(item))}")
                lines.append("\t]")
        else:
            lines.append(f"\t{key}: {_escape_snbt_string(str(value))}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def load_lang(path: Path) -> OrderedDict[str, Any]:
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as f:
            return OrderedDict(json.load(f))
    return parse_snbt_lang(path.read_text(encoding="utf-8"))


def load_lang_with_diagnostics(path: Path) -> tuple[OrderedDict[str, Any], dict[str, Any]]:
    """Load a lang file and return lightweight validation diagnostics.

    JSON duplicate keys are normally silently overwritten by json.load. For
    translation files this is dangerous, so v1.8 records duplicate keys before
    OrderedDict collapses them. SNBT duplicate detection is best-effort.
    """
    diagnostics: dict[str, Any] = {"duplicate_keys": 0, "duplicate_sample": []}
    if path.suffix.lower() == ".json":
        pairs_seen: Counter[str] = Counter()
        duplicates: list[str] = []

        def hook(pairs):
            out = OrderedDict()
            for k, v in pairs:
                if k in out:
                    pairs_seen[k] += 1
                    if k not in duplicates:
                        duplicates.append(k)
                out[k] = v
            return out

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f, object_pairs_hook=hook)
        diagnostics["duplicate_keys"] = len(duplicates)
        diagnostics["duplicate_sample"] = duplicates[:50]
        return OrderedDict(data), diagnostics

    text = path.read_text(encoding="utf-8")
    body = _strip_outer_braces(text)
    keys: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("#") or ":" not in line:
            continue
        k = line.split(":", 1)[0].strip().strip('"')
        if k:
            keys.append(k)
    dupes = [k for k, c in Counter(keys).items() if c > 1]
    diagnostics["duplicate_keys"] = len(dupes)
    diagnostics["duplicate_sample"] = dupes[:50]
    return parse_snbt_lang(text), diagnostics


def save_lang(data: dict[str, Any], path: Path, fmt: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt or path.suffix.lower().lstrip(".")
    if fmt == "json":
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif fmt == "snbt":
        path.write_text(dump_snbt_lang(data), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported output format: {fmt}")


def resolve_paths(input_path: str | Path) -> dict[str, Path | None]:
    p = Path(input_path).expanduser()
    if p.is_file():
        return {"input": p, "ftbquests": None, "quests": None, "lang": p if p.name == "en_us.snbt" else None}

    # Allow passing the instance root.
    if (p / "config" / "ftbquests").exists():
        ftb = p / "config" / "ftbquests"
    # Allow passing config folder.
    elif (p / "ftbquests").exists() and p.name.lower() == "config":
        ftb = p / "ftbquests"
    # Allow passing ftbquests.
    elif p.name.lower() == "ftbquests":
        ftb = p
    # Allow passing quests.
    elif p.name.lower() == "quests":
        ftb = p.parent
    else:
        ftb = p

    quests = ftb / "quests"
    if not quests.exists() and ftb.name.lower() == "quests":
        quests = ftb
        ftb = ftb.parent

    lang_candidates = [
        quests / "lang" / "en_us.snbt",
        ftb / "lang" / "en_us.snbt",
        ftb / "en_us.snbt",
        p / "quests" / "lang" / "en_us.snbt",
        p / "lang" / "en_us.snbt",
        p / "en_us.snbt",
    ]
    lang = next((c for c in lang_candidates if c.exists()), None)

    # FTB Quests newer/exported layouts may store lang as a folder:
    #   config/ftbquests/quests/lang/en_us/*.snbt
    #   config/ftbquests/quests/lang/en_us/chapters/*.snbt
    lang_dir_candidates = [
        quests / "lang" / "en_us",
        ftb / "lang" / "en_us",
        p / "quests" / "lang" / "en_us",
        p / "lang" / "en_us",
    ]
    lang_dir = next((c for c in lang_dir_candidates if c.exists() and c.is_dir()), None)

    return {
        "input": p,
        "ftbquests": ftb if ftb.exists() else None,
        "quests": quests if quests.exists() else None,
        "lang": lang,
        "lang_dir": lang_dir,
    }


def find_default_source(path: str | Path) -> Path:
    resolved = resolve_paths(path)
    lang = resolved.get("lang")
    if lang:
        return Path(lang)
    p = Path(path)
    raise FileNotFoundError(
        "Cannot find en_us.snbt. Tried instance/config/ftbquests/quests/lang/en_us.snbt, "
        f"ftbquests/quests/lang/en_us.snbt, lang/en_us.snbt, and en_us.snbt under: {p}"
    )



def _locale_lang_dir(root: Path, quests: Path | None, ftb: Path | None, locale: str) -> Path | None:
    """Find a folder-based FTBQ lang directory for a locale.

    Examples:
      config/ftbquests/quests/lang/en_us/
      config/ftbquests/lang/en_us/
    """
    candidates: list[Path] = []
    if quests:
        candidates.append(Path(quests) / "lang" / locale)
    if ftb:
        candidates.append(Path(ftb) / "lang" / locale)
    candidates.extend([
        root / "quests" / "lang" / locale,
        root / "lang" / locale,
    ])
    return next((p for p in candidates if p.exists() and p.is_dir()), None)


def _load_folder_lang(folder: Path) -> tuple[OrderedDict[str, Any], list[str]]:
    """Load and merge all JSON/SNBT lang files under a folder locale.

    Keys are kept as-is. For duplicate keys, the first file in sorted order wins.
    """
    merged: OrderedDict[str, Any] = OrderedDict()
    sources: list[str] = []
    for src in sorted([*folder.rglob("*.snbt"), *folder.rglob("*.json")]):
        try:
            data = load_lang(src)
        except Exception:
            continue
        if not data:
            continue
        sources.append(str(src))
        for k, v in data.items():
            if k not in merged:
                merged[k] = v
    return merged, sources


def is_probably_translatable_raw_string(s: str) -> bool:
    t = s.strip()
    if not t:
        return False
    low = t.lower()
    if low in RAW_SKIP_VALUES:
        return False
    if RESOURCE_LOCATION_RE.match(low):
        return False
    if HEX_ID_RE.match(t):
        return False
    if NUMERIC_RE.match(t):
        return False
    if URL_RE.match(t):
        return False
    if FILELIKE_RE.match(t):
        return False
    if low.startswith("#") and ":" in low:
        return False
    # A pure technical token with no spaces and only identifier chars is usually not player text.
    if TRANSLATION_REF_RE.match(t) and not any(c.isspace() for c in t) and not any(c in t for c in "&!?.,'\""):
        return False
    # Keep strings with spaces or punctuation typical for human text.
    if any(c.isspace() for c in t):
        return True
    if any(c in t for c in "!?.,'\"()[]&§"):
        return True
    # Single words can be titles, but only if they look human-ish.
    if len(t) >= 4 and re.match(r"^[A-Z][A-Za-z-]+$", t):
        return True
    return False


def extract_quoted_strings_with_lines(text: str) -> list[dict[str, Any]]:
    out = []
    for m in re.finditer(r'"((?:\\.|[^"\\])*)"', text):
        try:
            value = _unescape_snbt_string(m.group(1))
        except Exception:
            value = m.group(1)
        line = text.count("\n", 0, m.start()) + 1
        out.append({"line": line, "value": value})
    return out


def raw_snbt_files(quests: Path) -> list[Path]:
    files = []
    for rel in ["data.snbt", "chapter_groups.snbt"]:
        f = quests / rel
        if f.exists():
            files.append(f)
    for folder in ["chapters", "reward_tables"]:
        d = quests / folder
        if d.exists():
            files.extend(sorted(d.glob("*.snbt")))
    return files



FTBQUESTS_KEY_RE = re.compile(r"\bftbquests(?:\.[A-Za-z0-9_:-]+)+\b")


def extract_raw_key_refs(quests: Path) -> list[dict[str, Any]]:
    """Extract ftbquests translation keys from raw FTB Quests SNBT files.

    v0.8 change:
    Earlier versions only detected strings that were exactly "{ftbquests...}".
    Real packs also contain keys in places like:
      - hover: ["ftbquests.chapter.artifacts.image.hovertext1"]
      - JSON rich text: {"translate":"ftbquests.chapter.foo.questID.rich_description1"}

    This scans every quoted string and extracts any embedded ftbquests.* key.
    """
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for f in raw_snbt_files(quests):
        text = f.read_text(encoding="utf-8")
        for item in extract_quoted_strings_with_lines(text):
            value = item["value"].strip()
            for m in FTBQUESTS_KEY_RE.finditer(value):
                key = m.group(0).strip()
                if not key.startswith("ftbquests."):
                    continue
                ident = (str(f), key)
                if ident in seen:
                    continue
                seen.add(ident)
                refs.append({"file": str(f), "line": item["line"], "key": key, "raw": value})
    return refs




def _chapter_slug_from_path(path: Path) -> str:
    return path.stem


def _line_number_from_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _nearest_hex_id_before(text: str, offset: int) -> str | None:
    """Best-effort: find nearest FTB quest id before a text field."""
    window = text[max(0, offset - 12000):offset]
    matches = list(re.finditer(r'\bid\s*:\s*"([0-9A-Fa-f]{8,32})"', window))
    if not matches:
        return None
    return matches[-1].group(1).upper()


def _extract_snbt_array_strings_after(text: str, start_offset: int) -> list[tuple[str, int]]:
    """Extract quoted strings from a value immediately following a field name.

    This is intentionally lightweight, not a full SNBT parser. It is used only
    for known FTBQ text fields such as rich_description and hovertext.
    """
    colon = text.find(":", start_offset)
    if colon == -1:
        return []
    i = colon + 1
    n = len(text)
    while i < n and text[i].isspace():
        i += 1

    # String value: field: "..."
    if i < n and text[i] == '"':
        m = re.match(r'"((?:\\.|[^"\\])*)"', text[i:])
        if not m:
            return []
        try:
            value = _unescape_snbt_string(m.group(1))
        except Exception:
            value = m.group(1)
        return [(value, _line_number_from_offset(text, i))]

    # Array value: field: [ "...", "..." ]
    if i >= n or text[i] != "[":
        return []

    depth = 0
    in_str = False
    esc = False
    end = i
    while end < n:
        ch = text[end]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end += 1
                    break
        end += 1

    segment = text[i:end]
    values: list[tuple[str, int]] = []
    for m in re.finditer(r'"((?:\\.|[^"\\])*)"', segment):
        abs_pos = i + m.start()
        try:
            value = _unescape_snbt_string(m.group(1))
        except Exception:
            value = m.group(1)
        values.append((value, _line_number_from_offset(text, abs_pos)))
    return values


def extract_raw_generated_keys(quests: Path) -> list[dict[str, Any]]:
    """Infer Localizer-generated keys for raw human-text fields.

    Some FTB Quests content is not stored as {ftbquests...} references yet.
    FTB Quest Localizer generates keys for known text fields, most notably:
      - rich_description -> ftbquests.chapter.<chapter>.quest<ID>.rich_descriptionN
      - hovertext        -> ftbquests.chapter.<chapter>.image.hovertextN

    This function mirrors those key names well enough for raw-template export
    and comparison against Localizer output.
    """
    generated: list[dict[str, Any]] = []
    seen: set[str] = set()

    for f in raw_snbt_files(quests):
        path = Path(f)
        if path.parent.name != "chapters":
            continue
        chapter = _chapter_slug_from_path(path)
        text = path.read_text(encoding="utf-8")

        # Quest-level rich descriptions.
        for m in re.finditer(r'\brich_description\b\s*:', text):
            quest_id = _nearest_hex_id_before(text, m.start())
            if not quest_id:
                continue
            idx = 1
            for value, line in _extract_snbt_array_strings_after(text, m.start()):
                # Existing translation refs are already handled by extract_raw_key_refs.
                stripped = value.strip()
                if stripped.startswith("{ftbquests.") and stripped.endswith("}"):
                    continue
                if not is_probably_translatable_raw_string(value):
                    continue
                key = f"ftbquests.chapter.{chapter}.quest{quest_id}.rich_description{idx}"
                idx += 1
                if key in seen:
                    continue
                seen.add(key)
                generated.append({"file": str(path), "line": line, "key": key, "field": "rich_description", "source": value})

        # Chapter/image-level hover text.
        hover_idx = 1
        for m in re.finditer(r'\bhovertext\b\s*:', text):
            for value, line in _extract_snbt_array_strings_after(text, m.start()):
                stripped = value.strip()
                if stripped.startswith("{ftbquests.") and stripped.endswith("}"):
                    continue
                if not is_probably_translatable_raw_string(value):
                    continue
                key = f"ftbquests.chapter.{chapter}.image.hovertext{hover_idx}"
                hover_idx += 1
                if key in seen:
                    continue
                seen.add(key)
                generated.append({"file": str(path), "line": line, "key": key, "field": "hovertext", "source": value})

    return generated


def raw_key_template(quests: Path, mode: str = "blank") -> OrderedDict[str, Any]:
    refs = extract_raw_key_refs(quests)
    generated = extract_raw_generated_keys(quests)
    keys = sorted({r["key"] for r in refs} | {r["key"] for r in generated})
    out: OrderedDict[str, Any] = OrderedDict()
    for key in keys:
        if mode == "blank":
            out[key] = ""
        elif mode == "copy-key":
            out[key] = key
        else:
            raise ValueError(f"Unknown raw template mode: {mode}")
    return out


def scan_raw(quests: Path) -> dict[str, Any]:
    candidates = []
    all_strings = Counter()
    files = raw_snbt_files(quests)
    for f in files:
        text = f.read_text(encoding="utf-8")
        for item in extract_quoted_strings_with_lines(text):
            value = item["value"]
            all_strings[value] += 1
            if is_probably_translatable_raw_string(value):
                candidates.append({
                    "file": str(f),
                    "line": item["line"],
                    "text": value,
                })
    return {
        "mode": "raw",
        "note": "No quests/lang/en_us.snbt found. Raw mode found candidate strings and translation references. Use export-raw to create a blank key template.",
        "quests_dir": str(quests),
        "files_scanned": len(files),
        "quoted_strings_seen": sum(all_strings.values()),
        "unique_quoted_strings_seen": len(all_strings),
        "candidate_texts": len(candidates),
        "raw_translation_refs": len(extract_raw_key_refs(quests)),
        "generated_raw_keys": len(extract_raw_generated_keys(quests)),
        "candidate_sample": candidates[:50],
        "most_common_strings": all_strings.most_common(20),
    }


def blank_template(source: OrderedDict[str, Any], mode: str) -> OrderedDict[str, Any]:
    out: OrderedDict[str, Any] = OrderedDict()
    for k, v in source.items():
        if mode == "blank":
            out[k] = ["" for _ in v] if isinstance(v, list) else ""
        elif mode == "copy-source":
            out[k] = v
        else:
            raise ValueError(f"Unknown template mode: {mode}")
    return out


def merge_translation(source: OrderedDict[str, Any], old: dict[str, Any] | None, mode: str) -> OrderedDict[str, Any]:
    out = blank_template(source, mode=mode)
    if old:
        for k in source:
            if k in old:
                out[k] = old[k]
    return out


def stats(data: dict[str, Any]) -> dict[str, int]:
    strings = arrays = array_items = 0
    for v in data.values():
        if isinstance(v, list):
            arrays += 1
            array_items += len(v)
        else:
            strings += 1
    return {"keys": len(data), "string_values": strings, "array_values": arrays, "array_items": array_items, "total_text_units": strings + array_items}



LANG_FILENAME_RE = re.compile(r"^(en_us|zh_tw|zh_cn|ja_jp|ko_kr|[a-z]{2}_[a-z]{2})\.(json|snbt)$", re.I)


def _is_under_lang_dir(path: Path) -> bool:
    return any(part.lower() == "lang" for part in path.parts)


def _score_lang_file(path: Path) -> int:
    """Higher score = better source for FTBQ text resolution."""
    lower = str(path).lower().replace("\\", "/")
    score = 0
    if "/config/ftbquests/quests/lang/" in lower or lower.endswith("/ftbquests/quests/lang/en_us.snbt"):
        score += 1000
    if "/kubejs/assets/ftbquestlocalizer/lang/" in lower:
        score += 900
    if "/kubejs/assets/" in lower and "/lang/" in lower:
        score += 500
    if "/resourcepacks/" in lower and "/lang/" in lower:
        score += 300
    if path.name.lower() == "en_us.snbt":
        score += 50
    if path.name.lower() == "en_us.json":
        score += 40
    # Prefer shorter paths when scores tie.
    score -= min(len(path.parts), 80)
    return score


def find_lang_files(root: Path, locale: str = "en_us") -> list[Path]:
    """Find likely Minecraft/FTBQ language files without scanning huge mods jars."""
    root = Path(root)
    candidates: list[Path] = []
    wanted = {f"{locale}.json", f"{locale}.snbt"}
    skip_dirs = {"mods", "saves", "logs", "shaderpacks", "screenshots", "crash-reports", "backups"}
    for base in [root, root / "config", root / "kubejs", root / "resourcepacks", root / "defaultconfigs"]:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            parts_lower = {x.lower() for x in path.parts}
            if parts_lower & skip_dirs:
                continue
            if path.name.lower() in wanted and (_is_under_lang_dir(path) or path.suffix.lower() == ".snbt"):
                candidates.append(path)
    # Deduplicate and rank.
    uniq = sorted(set(candidates), key=lambda p: (-_score_lang_file(p), str(p).lower()))
    return uniq


def resolve_texts(pack_path: str | Path, locale: str = "en_us", raw_fallback: bool = True) -> tuple[OrderedDict[str, Any], dict[str, Any]]:
    """Resolve key -> source text using multiple fallback modes.

    Mode priority:
      A. config/ftbquests/quests/lang/en_us.snbt via resolve_paths()
      B. any discovered en_us.json/en_us.snbt under kubejs/assets or resourcepacks
      C. raw quest key template with blank values
    """
    root = Path(pack_path).expanduser()
    resolved = resolve_paths(root)
    report: dict[str, Any] = {
        "input": str(root),
        "locale": locale,
        "resolved_ftbquests": str(resolved.get("ftbquests")) if resolved.get("ftbquests") else None,
        "resolved_quests": str(resolved.get("quests")) if resolved.get("quests") else None,
        "mode": None,
        "source_files": [],
        "keys": 0,
        "blank_values": 0,
    }

    # A. Native FTBQ lang mode.
    # Supports both single-file layout:
    #   config/ftbquests/quests/lang/en_us.snbt
    # and folder layout:
    #   config/ftbquests/quests/lang/en_us/*.snbt
    if locale == "en_us" and resolved.get("lang"):
        src = Path(resolved["lang"])
        data = load_lang(src)
        report.update({"mode": "native-ftbquests-lang", "source_files": [str(src)], "keys": len(data)})
        return data, report

    lang_dir = _locale_lang_dir(root, resolved.get("quests"), resolved.get("ftbquests"), locale)
    if lang_dir:
        data, sources = _load_folder_lang(lang_dir)
        if data:
            report.update({
                "mode": "native-ftbquests-lang-folder",
                "source_files": sources,
                "keys": len(data),
                "lang_dir": str(lang_dir),
            })
            return data, report

    # B. Search language files. Merge in priority order, keeping the first value for duplicate keys.
    merged: OrderedDict[str, Any] = OrderedDict()
    sources: list[str] = []
    for lf in find_lang_files(root, locale=locale):
        try:
            data = load_lang(lf)
        except Exception:
            continue
        ftbq_items = [(k, v) for k, v in data.items() if str(k).startswith("ftbquests.")]
        if not ftbq_items:
            continue
        sources.append(str(lf))
        for k, v in ftbq_items:
            if k not in merged:
                merged[k] = v
    if merged:
        report.update({"mode": "discovered-lang-files", "source_files": sources, "keys": len(merged)})
        return merged, report

    # C. Raw fallback: can identify keys but not source text.
    quests = resolved.get("quests")
    if raw_fallback and quests:
        data = raw_key_template(Path(quests), mode="blank")
        report.update({"mode": "raw-blank-fallback", "source_files": [str(quests)], "keys": len(data), "blank_values": len(data)})
        return data, report

    raise FileNotFoundError(f"Could not resolve any {locale} FTBQ text source under: {root}")



# ---------- v1.5 manifest / inject ----------

def _path_is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _relpath_for_manifest(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace('\\', '/')
    except Exception:
        return str(path).replace('\\', '/')


def _manifest_value_type(value: Any) -> str:
    if isinstance(value, list):
        return "list"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def _manifest_line_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 1


def build_manifest_for_resolved(pack_path: str | Path, locale: str, data: OrderedDict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Build a source manifest for the resolved lang data.

    v1.5 records enough information to send translated keys back to the
    same language-file system they came from. It does not store line numbers;
    inject rebuilds lang files from key/value data.
    """
    root = Path(pack_path).expanduser()
    sources = [Path(x) for x in report.get("source_files", [])]
    source_entries: list[dict[str, Any]] = []
    source_id_by_path: dict[str, int] = {}

    for src in sources:
        sid = len(source_entries)
        source_id_by_path[str(src)] = sid
        fmt = src.suffix.lower().lstrip('.') or 'json'
        rel = _relpath_for_manifest(src, root)
        source_entries.append({
            "id": sid,
            "source": "ftbquests",
            "adapter": "ftbquests",
            "source_file": str(src),
            "relative_path": rel,
            "format": fmt,
            "source_locale": locale,
            "mode": report.get("mode"),
        })

    key_sources: OrderedDict[str, dict[str, Any]] = OrderedDict()

    # Native FTBQ mode can be one source file containing all native keys.
    if report.get("mode") == "native-ftbquests-lang" and sources:
        sid = 0
        for key, value in data.items():
            key_sources[key] = {
                "source_id": sid,
                "value_type": _manifest_value_type(value),
                "line_count": _manifest_line_count(value),
            }

    # Folder-based native FTBQ lang mode assigns keys back to the file where
    # they were first found.
    elif report.get("mode") == "native-ftbquests-lang-folder" and sources:
        assigned: set[str] = set()
        for src in sources:
            sid = source_id_by_path[str(src)]
            try:
                src_data = load_lang(src)
            except Exception:
                continue
            for key in src_data.keys():
                if key in data and key not in assigned:
                    value = data[key]
                    key_sources[key] = {
                        "source": "ftbquests",
                        "adapter": "ftbquests",
                        "source_id": sid,
                        "value_type": _manifest_value_type(value),
                        "line_count": _manifest_line_count(value),
                    }
                    assigned.add(key)
        for key, value in data.items():
            key_sources.setdefault(key, {
                "source": "ftbquests",
                "adapter": "ftbquests",
                "source_id": 0,
                "value_type": _manifest_value_type(value),
                "line_count": _manifest_line_count(value),
            })

    # Discovered lang files may be many files. Re-load in same priority order
    # and assign each key to the first source that contributed it.
    elif report.get("mode") == "discovered-lang-files" and sources:
        assigned: set[str] = set()
        for src in sources:
            sid = source_id_by_path[str(src)]
            try:
                src_data = load_lang(src)
            except Exception:
                continue
            for key in src_data.keys():
                if key in data and key not in assigned:
                    value = data[key]
                    key_sources[key] = {
                        "source": "ftbquests",
                        "adapter": "ftbquests",
                        "source_id": sid,
                        "value_type": _manifest_value_type(value),
                        "line_count": _manifest_line_count(value),
                    }
                    assigned.add(key)
        # Fallback: assign anything missing to first source.
        for key, value in data.items():
            key_sources.setdefault(key, {
                "source": "ftbquests",
                "adapter": "ftbquests",
                "source_id": 0,
                "value_type": _manifest_value_type(value),
                "line_count": _manifest_line_count(value),
            })

    # Raw blank fallback has no concrete text source for each key, but keep a
    # manifest anyway so validation can still operate.
    else:
        if not source_entries:
            source_entries.append({
                "id": 0,
                "source": "ftbquests",
                "adapter": "ftbquests",
                "source_file": str(root),
                "relative_path": ".",
                "format": "json",
                "source_locale": locale,
                "mode": report.get("mode"),
            })
        for key, value in data.items():
            key_sources[key] = {
                "source": "ftbquests",
                "adapter": "ftbquests",
                "source_id": 0,
                "raw_fallback": True,
                "value_type": _manifest_value_type(value),
                "line_count": _manifest_line_count(value),
            }

    return {
        "qlf_manifest_version": 3,
        "source_system": "adapter",
        "pack_root": str(root),
        "source_locale": locale,
        "mode": report.get("mode"),
        "sources": source_entries,
        "keys": key_sources,
    }


def _target_relative_path(rel: str, source_locale: str, target_locale: str) -> str:
    p = Path(rel)
    parts = list(p.parts)

    # Folder-based locale layout:
    #   config/ftbquests/quests/lang/en_us/chapters/create.snbt
    # becomes:
    #   config/ftbquests/quests/lang/zh_tw/chapters/create.snbt
    for i, part in enumerate(parts):
        if part.lower() == source_locale.lower():
            parts[i] = target_locale
            return str(Path(*parts)).replace('\\', '/')

    name = p.name
    for ext in ('.json', '.snbt', '.lang'):
        old = f"{source_locale}{ext}"
        if name.lower() == old.lower():
            return str(p.with_name(f"{target_locale}{ext}")).replace('\\', '/')

    # If the source file did not use the locale as folder or filename, append target locale.
    if p.suffix:
        return str(p.with_name(f"{p.stem}.{target_locale}{p.suffix}")).replace('\\', '/')
    return str(p / target_locale).replace('\\', '/')


def inject_from_manifest(translation: OrderedDict[str, Any], manifest: dict[str, Any], target_locale: str, out_dir: Path, *, strict: bool = True, backup_existing: bool = True) -> dict[str, Any]:
    manifest_keys = list(manifest.get("keys", {}).keys())
    manifest_key_set = set(manifest_keys)
    trans_key_set = set(translation.keys())
    missing = sorted(manifest_key_set - trans_key_set)
    extra = sorted(trans_key_set - manifest_key_set)
    if strict and missing:
        raise ValueError(
            "Translation is missing manifest keys. "
            f"missing={len(missing)}, extra={len(extra)}. "
            "Run validate or fix the translated file before inject."
        )

    sources = {int(s["id"]): s for s in manifest.get("sources", [])}
    source_locale = manifest.get("source_locale", "en_us")
    grouped: dict[int, OrderedDict[str, Any]] = {}
    skipped_extra = 0
    for key, value in translation.items():
        kinfo = manifest.get("keys", {}).get(key)
        if not kinfo:
            skipped_extra += 1
            continue
        sid = int(kinfo["source_id"])
        grouped.setdefault(sid, OrderedDict())[key] = value

    written: list[dict[str, Any]] = []
    backups: list[dict[str, str]] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for sid, data in grouped.items():
        src = sources.get(sid)
        if not src:
            continue
        rel = src.get("relative_path") or Path(src.get("source_file", f"source_{sid}.json")).name
        target_rel = _target_relative_path(rel, source_locale, target_locale)
        out_path = out_dir / target_rel
        fmt = src.get("format") or out_path.suffix.lower().lstrip('.') or 'json'
        backup_path = None
        if backup_existing and out_path.exists():
            backup_path = out_path.with_name(out_path.name + ".bak")
            n = 1
            while backup_path.exists():
                backup_path = out_path.with_name(out_path.name + f".bak{n}")
                n += 1
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(out_path, backup_path)
            backups.append({"original": str(out_path), "backup": str(backup_path)})
        save_lang(data, out_path, fmt=fmt)
        item = {
            "source_id": sid,
            "source": src.get("source", "ftbquests"),
            "adapter": src.get("adapter", src.get("source", "ftbquests")),
            "keys": len(data),
            "format": fmt,
            "out": str(out_path),
        }
        if backup_path:
            item["backup"] = str(backup_path)
        written.append(item)

    return {
        "manifest_keys": len(manifest_key_set),
        "translation_keys": len(translation),
        "missing_keys": len(missing),
        "extra_keys": len(extra),
        "skipped_extra_keys": skipped_extra,
        "written_files": len(written),
        "written": written,
        "backups_created": len(backups),
        "backups": backups,
        "missing_sample": missing[:50],
        "extra_sample": extra[:50],
    }


# ---------- v1.1 key mapping / normalization ----------

def build_ftbq_index(path: str | Path) -> dict[str, Any]:
    """Build a lightweight ID index from raw FTB Quests chapter files.

    This is not a full SNBT parser. It is a pragmatic mapper for localization keys:
      native FTBQ key:    quest.<ID>.title
      Localizer key:      ftbquests.chapter.<chapter_slug>.quest<ID>.title
    """
    resolved = resolve_paths(path)
    quests = resolved.get("quests")
    if not quests:
        raise FileNotFoundError(f"Cannot locate ftbquests/quests under: {path}")
    quests = Path(quests)
    chapters_dir = quests / "chapters"
    if not chapters_dir.exists():
        raise FileNotFoundError(f"Cannot locate chapters folder under: {quests}")

    chapter_by_id: dict[str, str] = {}
    quest_to_chapter: dict[str, str] = {}
    task_to_parent: dict[str, dict[str, str]] = {}
    reward_table_by_id: dict[str, str] = {}

    # Reward tables can also have native lang keys like reward_table.<ID>.title.
    # Index them by their top-level id from quests/reward_tables/*.snbt.
    reward_tables_dir = quests / "reward_tables"
    if reward_tables_dir.exists():
        for rt_file in sorted(reward_tables_dir.glob("*.snbt")):
            rt_text = rt_file.read_text(encoding="utf-8")
            rt_top = rt_text.split("rewards:", 1)[0]
            m_rt = re.search(r'\bid\s*:\s*"([0-9A-Fa-f]{8,32})"', rt_top)
            if m_rt:
                reward_table_by_id[m_rt.group(1).upper()] = rt_file.stem

    for chapter_file in sorted(chapters_dir.glob("*.snbt")):
        slug = chapter_file.stem
        text = chapter_file.read_text(encoding="utf-8")

        # Chapter id usually appears near top-level before quests list.
        top = text.split("quests:", 1)[0]
        m_ch = re.search(r'\bid\s*:\s*"([0-9A-Fa-f]{8,32})"', top)
        if m_ch:
            chapter_by_id[m_ch.group(1).upper()] = slug

        # Walk ID lines by indentation. FTBQ chapter SNBT is consistently indented:
        #   chapter id: 1 tab
        #   quest id:   3 tabs
        #   task id:    5+ tabs under current quest
        # This avoids confusing reward IDs with quest IDs.
        current_quest: str | None = None
        for line in text.splitlines():
            m_id = re.match(r'^(\s*)id\s*:\s*"([0-9A-Fa-f]{8,32})"', line)
            if not m_id:
                continue
            indent = m_id.group(1).count("\t") + (len(m_id.group(1).replace("\t", "")) // 4)
            obj_id = m_id.group(2).upper()
            if indent == 3:
                current_quest = obj_id
                quest_to_chapter[obj_id] = slug
            elif indent >= 4 and current_quest:
                task_to_parent[obj_id] = {"chapter": slug, "quest": current_quest}

    return {
        "quests_dir": str(quests),
        "chapter_by_id": chapter_by_id,
        "quest_to_chapter": quest_to_chapter,
        "task_to_parent": task_to_parent,
        "reward_table_by_id": reward_table_by_id,
    }


def _localizer_id(obj_id: str) -> str:
    """FTB Quest Localizer-style IDs usually drop leading zeros."""
    obj_id = str(obj_id).upper()
    return obj_id.lstrip("0") or "0"

def native_key_to_localizer_key(key: str, index: dict[str, Any]) -> str | None:
    """Map native FTBQ lang key to FTB Quest Localizer-style key when possible."""
    chapter_by_id = index.get("chapter_by_id", {})
    quest_to_chapter = index.get("quest_to_chapter", {})
    task_to_parent = index.get("task_to_parent", {})
    reward_table_by_id = index.get("reward_table_by_id", {})

    m = re.fullmatch(r"chapter\.([0-9A-Fa-f]+)\.title", key)
    if m:
        slug = chapter_by_id.get(m.group(1).upper())
        return f"ftbquests.chapter.{slug}.title" if slug else None

    m = re.fullmatch(r"chapter\.([0-9A-Fa-f]+)\.chapter_subtitle", key)
    if m:
        slug = chapter_by_id.get(m.group(1).upper())
        return f"ftbquests.chapter.{slug}.subtitle" if slug else None

    m = re.fullmatch(r"chapter_group\.([0-9A-Fa-f]+)\.title", key)
    if m:
        return f"ftbquests.chapter_groups.{m.group(1).upper()}.title"

    m = re.fullmatch(r"quest\.([0-9A-Fa-f]+)\.title", key)
    if m:
        qid = m.group(1).upper()
        slug = quest_to_chapter.get(qid)
        return f"ftbquests.chapter.{slug}.quest{_localizer_id(qid)}.title" if slug else None

    m = re.fullmatch(r"quest\.([0-9A-Fa-f]+)\.quest_subtitle", key)
    if m:
        qid = m.group(1).upper()
        slug = quest_to_chapter.get(qid)
        return f"ftbquests.chapter.{slug}.quest{_localizer_id(qid)}.subtitle" if slug else None

    m = re.fullmatch(r"quest\.([0-9A-Fa-f]+)\.quest_desc", key)
    if m:
        qid = m.group(1).upper()
        slug = quest_to_chapter.get(qid)
        return f"ftbquests.chapter.{slug}.quest{_localizer_id(qid)}.description" if slug else None

    m = re.fullmatch(r"reward_table\.([0-9A-Fa-f]+)\.title", key)
    if m:
        rid = m.group(1).upper()
        # FTB Quest Localizer has used ftbquests.loot_table.<ID>.title for reward tables.
        # Keep the ID normalized in the same no-leading-zero style.
        return f"ftbquests.loot_table.{_localizer_id(rid)}.title"

    m = re.fullmatch(r"task\.([0-9A-Fa-f]+)\.title", key)
    if m:
        tid = m.group(1).upper()
        parent = task_to_parent.get(tid)
        if parent:
            return f"ftbquests.chapter.{parent['chapter']}.quest{_localizer_id(parent['quest'])}.task.{_localizer_id(tid)}.title"
        return None

    return None


def _nonblank_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip() != ""]
    if str(value).strip() == "":
        return []
    return [str(value)]


def _infer_localizer_key_from_reference(native_key: str, value: Any, reference: dict[str, Any]) -> str | None:
    """Infer Localizer-style key by matching text values against a reference Localizer lang.

    This is a fallback for stale native lang entries whose IDs are not present in
    current chapter files. It should only be trusted when the matched text is unique.
    """
    items = _nonblank_items(value)
    if not items:
        return None

    def unique(candidates: list[str]) -> str | None:
        candidates = sorted(set(candidates))
        return candidates[0] if len(candidates) == 1 else None

    # Native arrays: quest.<id>.quest_desc -> Localizer prefix.description1/2/...
    if re.fullmatch(r"quest\.[0-9A-Fa-f]+\.quest_desc", native_key):
        first = items[0]
        cands = [k[:-1] for k, v in reference.items() if k.endswith(".description1") and str(v) == first]
        return unique(cands)  # returns prefix ending with .description

    suffixes: list[str] = []
    if native_key.endswith(".title"):
        suffixes = [".title"]
    elif native_key.endswith(".quest_subtitle") or native_key.endswith(".chapter_subtitle"):
        suffixes = [".subtitle"]
    elif native_key.endswith(".quest_desc"):
        suffixes = [".description"]

    if not suffixes:
        return None
    text = items[0]
    cands = [k for k, v in reference.items() if any(k.endswith(suf) for suf in suffixes) and str(v) == text]
    return unique(cands)


def convert_native_to_localizer(
    data: OrderedDict[str, Any],
    index: dict[str, Any],
    split_arrays: bool = True,
    reference: dict[str, Any] | None = None,
    keep_unmapped: bool = False,
) -> tuple[OrderedDict[str, Any], dict[str, Any]]:
    out: OrderedDict[str, Any] = OrderedDict()
    unmapped: list[str] = []
    reference_mapped_keys: list[str] = []
    kept_unmapped = 0
    expanded_arrays = 0
    mapped = 0

    for key, value in data.items():
        mapped_key = native_key_to_localizer_key(key, index)
        used_reference = False
        if not mapped_key and reference is not None:
            mapped_key = _infer_localizer_key_from_reference(key, value, reference)
            used_reference = mapped_key is not None

        if not mapped_key:
            unmapped.append(key)
            if keep_unmapped:
                out[f"__unmapped__.{key}"] = value
                kept_unmapped += 1
            continue

        # quest_desc arrays become description1, description2, ... in Localizer style.
        if mapped_key.endswith(".description") and isinstance(value, list) and split_arrays:
            n = 1
            for item in value:
                # Match Localizer behavior: blank lines generally do not become descriptionN.
                if str(item).strip() == "":
                    continue
                out[f"{mapped_key}{n}"] = item
                n += 1
            expanded_arrays += 1
            mapped += 1
        else:
            out[mapped_key] = value
            mapped += 1
        if used_reference:
            reference_mapped_keys.append(key)

    report = {
        "input_keys": len(data),
        "output_keys": len(out),
        "mapped_native_keys": mapped,
        "unmapped_native_keys": len(unmapped),
        "reference_mapped_native_keys": len(reference_mapped_keys),
        "kept_unmapped_keys": kept_unmapped,
        "expanded_arrays": expanded_arrays,
        "unmapped_sample": unmapped[:50],
        "reference_mapped_sample": reference_mapped_keys[:50],
        "index_counts": {
            "chapters": len(index.get("chapter_by_id", {})),
            "quests": len(index.get("quest_to_chapter", {})),
            "tasks": len(index.get("task_to_parent", {})),
            "reward_tables": len(index.get("reward_table_by_id", {})),
        },
    }
    return out, report




def _native_key_entity(key: str) -> tuple[str, str] | None:
    """Return (entity_type, id) for native FTBQ lang keys."""
    patterns = [
        ("chapter", r"chapter\.([0-9A-Fa-f]+)\.(?:title|chapter_subtitle)$"),
        ("chapter_group", r"chapter_group\.([0-9A-Fa-f]+)\.title$"),
        ("quest", r"quest\.([0-9A-Fa-f]+)\.(?:title|quest_subtitle|quest_desc)$"),
        ("reward_table", r"reward_table\.([0-9A-Fa-f]+)\.title$"),
        ("task", r"task\.([0-9A-Fa-f]+)\.title$"),
    ]
    for kind, pat in patterns:
        m = re.fullmatch(pat, key)
        if m:
            return kind, m.group(1).upper()
    return None


def _is_blank_value(value: Any) -> bool:
    if isinstance(value, list):
        return all(str(x).strip() == "" for x in value)
    return str(value).strip() == ""


def audit_native_lang(data: OrderedDict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    """Audit native FTBQ lang keys against raw quest/chapter indexes.

    This distinguishes real mapping failures from stale/orphan language entries.
    If a native key references a quest/task/chapter ID that does not exist in
    the current raw FTB Quests files, it is marked as orphan_*.
    """
    chapter_ids = set(index.get("chapter_by_id", {}))
    quest_ids = set(index.get("quest_to_chapter", {}))
    task_ids = set(index.get("task_to_parent", {}))
    reward_ids = set(index.get("reward_table_by_id", {}))

    buckets: dict[str, list[str]] = {
        "mapped": [],
        "orphan_chapter": [],
        "orphan_quest": [],
        "orphan_task": [],
        "orphan_reward_table": [],
        "unknown_native_format": [],
        "blank_values": [],
    }

    for key, value in data.items():
        if _is_blank_value(value):
            buckets["blank_values"].append(key)
        if native_key_to_localizer_key(key, index):
            buckets["mapped"].append(key)
            continue
        ent = _native_key_entity(key)
        if not ent:
            buckets["unknown_native_format"].append(key)
            continue
        kind, obj_id = ent
        if kind == "chapter" and obj_id not in chapter_ids:
            buckets["orphan_chapter"].append(key)
        elif kind == "quest" and obj_id not in quest_ids:
            buckets["orphan_quest"].append(key)
        elif kind == "task" and obj_id not in task_ids:
            buckets["orphan_task"].append(key)
        elif kind == "reward_table" and obj_id not in reward_ids:
            buckets["orphan_reward_table"].append(key)
        elif kind == "chapter_group":
            # chapter_groups are mapped without raw index dependency in native_key_to_localizer_key.
            buckets["unknown_native_format"].append(key)
        else:
            buckets["unknown_native_format"].append(key)

    counts = {k: len(v) for k, v in buckets.items()}
    orphan_total = counts["orphan_chapter"] + counts["orphan_quest"] + counts["orphan_task"] + counts["orphan_reward_table"]
    effective_total = len(data) - orphan_total
    effective_mapped = counts["mapped"]
    effective_coverage = (effective_mapped / effective_total * 100) if effective_total else 100.0

    return {
        "input_keys": len(data),
        "mapped": counts["mapped"],
        "orphan_total": orphan_total,
        "orphan_chapter": counts["orphan_chapter"],
        "orphan_quest": counts["orphan_quest"],
        "orphan_task": counts["orphan_task"],
        "orphan_reward_table": counts["orphan_reward_table"],
        "unknown_native_format": counts["unknown_native_format"],
        "blank_values": counts["blank_values"],
        "effective_total_without_orphans": effective_total,
        "effective_mapping_coverage_percent": round(effective_coverage, 2),
        "samples": {k: v[:50] for k, v in buckets.items() if k != "mapped"},
        "index_counts": {
            "chapters": len(index.get("chapter_by_id", {})),
            "quests": len(index.get("quest_to_chapter", {})),
            "tasks": len(index.get("task_to_parent", {})),
            "reward_tables": len(index.get("reward_table_by_id", {})),
        },
    }



# ---------- v1.7 debug / diff helpers ----------

def _jsonable_value_preview(value: Any, limit: int = 120) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
    return text if len(text) <= limit else text[:limit] + "..."


def diff_lang_data(old_data: OrderedDict[str, Any], new_data: OrderedDict[str, Any]) -> dict[str, Any]:
    old_keys = set(old_data)
    new_keys = set(new_data)
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    changed = sorted(k for k in (old_keys & new_keys) if old_data[k] != new_data[k])
    unchanged = len(old_keys & new_keys) - len(changed)
    return {
        "old_keys": len(old_data),
        "new_keys": len(new_data),
        "added": len(added),
        "removed": len(removed),
        "changed": len(changed),
        "unchanged": unchanged,
        "added_sample": added[:50],
        "removed_sample": removed[:50],
        "changed_sample": [
            {
                "key": k,
                "old": _jsonable_value_preview(old_data[k]),
                "new": _jsonable_value_preview(new_data[k]),
            }
            for k in changed[:50]
        ],
    }



def cmd_sources(args: argparse.Namespace) -> int:
    """List registered source adapters and optionally detect them in an instance."""
    adapters = {}
    if get_adapter_registry is not None:
        try:
            adapters = get_adapter_registry()
        except Exception:
            adapters = {}
    if not adapters:
        adapters = {"ftbquests": None}

    report = {
        "registered_adapters": sorted(adapters.keys()),
        "instance": str(args.instance) if getattr(args, "instance", None) else None,
        "detected": {},
    }
    if getattr(args, "instance", None):
        instance = Path(args.instance)
        for name, adapter in adapters.items():
            try:
                if adapter is not None and hasattr(adapter, "detect"):
                    info = adapter.detect(instance)
                elif name == "ftbquests":
                    r = resolve_paths(instance)
                    info = {
                        "detected": bool(r.get("ftbquests") and r.get("quests")),
                        "ftbquests": str(r.get("ftbquests")) if r.get("ftbquests") else None,
                        "quests": str(r.get("quests")) if r.get("quests") else None,
                        "lang": str(r.get("lang")) if r.get("lang") else None,
                    }
                else:
                    info = {"detected": False}
            except Exception as exc:
                info = {"detected": False, "error": str(exc)}
            report["detected"][name] = info

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def _adapter_report_entry(name: str, adapter: Any) -> dict[str, Any]:
    if adapter_info is not None:
        info = adapter_info(adapter)
    elif adapter is not None and hasattr(adapter, "info"):
        info = adapter.info()
    else:
        info = {
            "name": name,
            "version": getattr(adapter, "version", 0) if adapter is not None else 0,
            "description": getattr(adapter, "description", "") if adapter is not None else "",
            "source_scope": getattr(adapter, "source_scope", "unknown") if adapter is not None else "unknown",
            "capabilities": list(getattr(adapter, "capabilities", [])) if adapter is not None else [],
            "sdk": "qlf-adapter-v1",
        }
    info.setdefault("name", name)
    return info


def cmd_adapters(args: argparse.Namespace) -> int:
    """Show registered adapters with SDK metadata."""
    adapters = get_adapter_registry() if get_adapter_registry is not None else {"ftbquests": None}
    report = {
        "sdk": "qlf-adapter-v1",
        "registered_adapters": [
            _adapter_report_entry(name, adapter)
            for name, adapter in sorted(adapters.items())
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def cmd_adapter_info(args: argparse.Namespace) -> int:
    """Show SDK metadata for one adapter."""
    adapters = get_adapter_registry() if get_adapter_registry is not None else {"ftbquests": None}
    adapter = adapters.get(args.name)
    if adapter is None and args.name not in adapters:
        report = {
            "ok": False,
            "error": f"unknown adapter: {args.name}",
            "available": sorted(adapters.keys()),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.report:
            Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 1
    report = {
        "ok": True,
        "adapter": _adapter_report_entry(args.name, adapter),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def cmd_adapter_template(args: argparse.Namespace) -> int:
    """Write a starter adapter template to a target path."""
    adapter_name = (args.name or "myadapter").strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", adapter_name):
        raise ValueError("adapter name must be a valid Python identifier, e.g. patchouli or quest_kubejs")

    class_name = "".join(part.capitalize() for part in adapter_name.split("_")) + "Adapter"
    out = Path(args.out)
    if out.exists() and not args.force:
        raise FileExistsError(f"output already exists: {out} (use --force to overwrite)")
    out.parent.mkdir(parents=True, exist_ok=True)

    template = f"""from __future__ import annotations

from pathlib import Path
from typing import Any

from qlf_core.adapters.base import BaseAdapter


class {class_name}(BaseAdapter):
    name = \"{adapter_name}\"
    version = 1
    description = \"TODO: describe this quest-related source\"
    source_scope = \"quest-only: TODO describe allowed folders\"
    capabilities = [\"detect\"]

    def detect(self, instance_path: str | Path) -> dict[str, Any]:
        instance = Path(instance_path).expanduser()
        # TODO: replace with real detection logic.
        return {{
            \"detected\": False,
            \"instance\": str(instance),
            \"adapter\": self.name,
            \"capabilities\": list(self.capabilities),
            \"source_scope\": self.source_scope,
        }}

    def extract(self, instance_path: str | Path, locale: str = \"en_us\"):
        # TODO: return (translation_data, manifest_fragment).
        raise NotImplementedError

    def inject(self, *args: Any, **kwargs: Any):
        # TODO: write translated values back to this source.
        raise NotImplementedError
"""
    out.write_text(template, encoding="utf-8")
    report = {
        "ok": True,
        "sdk": "qlf-adapter-v1",
        "adapter_name": adapter_name,
        "class_name": class_name,
        "out": str(out),
        "next_steps": [
            "Edit metadata and detect() logic",
            "Register the adapter in qlf_core/adapters/registry.py",
            "Run: python qlf.py adapters",
            "Run: python qlf.py sources --instance <modpack>",
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0

def cmd_diff(args: argparse.Namespace) -> int:
    """v1.7 diff command.

    Compares two JSON/SNBT lang files. Optionally writes machine-readable
    added/removed/changed detail files for later sync/review workflows.
    """
    old_data = load_lang(Path(args.old))
    new_data = load_lang(Path(args.new))
    report = diff_lang_data(old_data, new_data)

    if args.added_out:
        added_keys = report["added_sample"] if args.sample_only else sorted(set(new_data) - set(old_data))
        save_lang(OrderedDict((k, new_data[k]) for k in added_keys), Path(args.added_out), fmt="json")
    if args.removed_out:
        removed_keys = report["removed_sample"] if args.sample_only else sorted(set(old_data) - set(new_data))
        save_lang(OrderedDict((k, old_data[k]) for k in removed_keys), Path(args.removed_out), fmt="json")
    if args.changed_out:
        changed_keys = sorted(k for k in (set(old_data) & set(new_data)) if old_data[k] != new_data[k])
        if args.sample_only:
            changed_keys = changed_keys[:50]
        changed_obj = OrderedDict()
        for k in changed_keys:
            changed_obj[k] = {"old": old_data[k], "new": new_data[k]}
        Path(args.changed_out).write_text(json.dumps(changed_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def cmd_debug(args: argparse.Namespace) -> int:
    """v1.7 debug command for QLF project state.

    It does not modify files. It checks:
    - instance/ftbquests/lang detection
    - manifest readability and source paths
    - translation key match
    - predicted output paths for inject
    """
    report: dict[str, Any] = {
        "checks": {},
        "errors": [],
        "warnings": [],
    }

    instance_root: Path | None = None
    if args.instance:
        instance_root = Path(args.instance).expanduser()
        r = resolve_paths(instance_root)
        report["instance"] = {
            "path": str(instance_root),
            "exists": instance_root.exists(),
            "resolved_ftbquests": str(r.get("ftbquests")) if r.get("ftbquests") else None,
            "resolved_quests": str(r.get("quests")) if r.get("quests") else None,
            "resolved_lang": str(r.get("lang")) if r.get("lang") else None,
        }
        if not instance_root.exists():
            report["errors"].append("instance path does not exist")
        if not r.get("quests"):
            report["warnings"].append("could not locate config/ftbquests/quests in instance")

    manifest = None
    if args.manifest:
        mp = Path(args.manifest)
        report["manifest"] = {"path": str(mp), "exists": mp.exists()}
        if not mp.exists():
            report["errors"].append("manifest file does not exist")
        else:
            try:
                manifest = json.loads(mp.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
                report["manifest"].update({
                    "version": manifest.get("qlf_manifest_version"),
                    "pack_root": manifest.get("pack_root"),
                    "mode": manifest.get("mode"),
                    "source_locale": manifest.get("source_locale"),
                    "sources": len(manifest.get("sources", [])),
                    "keys": len(manifest.get("keys", {})),
                })
            except Exception as exc:
                report["errors"].append(f"cannot read manifest: {exc}")

    translation = None
    if args.translation:
        tp = Path(args.translation)
        report["translation"] = {"path": str(tp), "exists": tp.exists()}
        if not tp.exists():
            report["errors"].append("translation file does not exist")
        else:
            try:
                translation = load_lang(tp)
                empty = [k for k, v in translation.items() if _is_blank_value(v)]
                report["translation"].update({"keys": len(translation), "empty_values": len(empty), "empty_sample": empty[:20]})
            except Exception as exc:
                report["errors"].append(f"cannot read translation: {exc}")

    if manifest and translation is not None:
        mkeys = set(manifest.get("keys", {}))
        tkeys = set(translation)
        missing = sorted(mkeys - tkeys)
        extra = sorted(tkeys - mkeys)
        report["key_check"] = {
            "manifest_keys": len(mkeys),
            "translation_keys": len(tkeys),
            "missing_keys": len(missing),
            "extra_keys": len(extra),
            "missing_sample": missing[:50],
            "extra_sample": extra[:50],
        }
        if missing:
            report["errors"].append("translation is missing keys from manifest")
        if extra:
            report["warnings"].append("translation has extra keys not present in manifest")

        source_locale = manifest.get("source_locale", "en_us")
        target_locale = args.locale
        out_root = Path(args.write_to_instance).expanduser() if args.write_to_instance else (Path(args.out_dir).expanduser() if args.out_dir else None)
        predicted = []
        for src in manifest.get("sources", []):
            rel = src.get("relative_path") or Path(src.get("source_file", f"source_{src.get('id', '?')}.json")).name
            target_rel = _target_relative_path(rel, source_locale, target_locale)
            item = {"source_id": src.get("id"), "source": rel, "target_relative_path": target_rel, "format": src.get("format")}
            if out_root:
                target_path = out_root / target_rel
                item["target_path"] = str(target_path)
                item["target_exists"] = target_path.exists()
                item["backup_would_be_created"] = bool(args.write_to_instance and target_path.exists() and not args.no_backup)
            predicted.append(item)
        report["predicted_outputs"] = predicted

    report["ok"] = not report["errors"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


def cmd_audit(args: argparse.Namespace) -> int:
    index = build_ftbq_index(args.ftbquests)
    data = load_lang(Path(args.input))
    report = audit_native_lang(data, index)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Nonzero only for unknown formats, not for orphans. Orphans are diagnostic information.
    return 1 if report.get("unknown_native_format", 0) else 0


def cmd_keymap(args: argparse.Namespace) -> int:
    index = build_ftbq_index(args.ftbquests)
    data = load_lang(Path(args.input))
    reference = load_lang(Path(args.reference_localizer)) if getattr(args, "reference_localizer", None) else None
    out_data, report = convert_native_to_localizer(
        data,
        index,
        split_arrays=not args.no_split_arrays,
        reference=reference,
        keep_unmapped=getattr(args, "keep_unmapped", False),
    )
    out_path = Path(args.out)
    fmt = args.format or out_path.suffix.lower().lstrip(".") or "json"
    save_lang(out_data, out_path, fmt=fmt)
    report.update({"out": str(out_path), "format": fmt})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if report["unmapped_native_keys"] else 0


def cmd_compare_mapped(args: argparse.Namespace) -> int:
    index = build_ftbq_index(args.ftbquests)
    native_data = load_lang(Path(args.native))
    other = load_lang(Path(args.other))
    mapped_data, map_report = convert_native_to_localizer(
        native_data,
        index,
        split_arrays=not args.no_split_arrays,
        reference=other if getattr(args, "use_other_as_reference", False) else None,
        keep_unmapped=False,
    )
    mapped_keys = set(mapped_data)
    other_keys = set(other)
    missing_in_other = sorted(mapped_keys - other_keys)
    extra_in_other = sorted(other_keys - mapped_keys)
    changed = sorted(k for k in (mapped_keys & other_keys) if mapped_data[k] != other[k])
    report = {
        "mapped_keys": len(mapped_data),
        "other_keys": len(other),
        "missing_in_other": len(missing_in_other),
        "extra_in_other": len(extra_in_other),
        "changed_values": len(changed),
        "missing_sample": missing_in_other[:50],
        "extra_sample": extra_in_other[:50],
        "changed_sample": changed[:50],
        "map_report": map_report,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if missing_in_other or extra_in_other else 0


def cmd_locate(args: argparse.Namespace) -> int:
    r = resolve_paths(args.path)
    report: dict[str, Any] = {k: (str(v) if v else None) for k, v in r.items()}
    q = r.get("quests")
    if q:
        q = Path(q)
        report["quests_children"] = sorted([x.name for x in q.iterdir()])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    resolved = resolve_paths(args.ftbquests)
    lang = resolved.get("lang")
    if lang:
        src = Path(lang)
        data = load_lang(src)
        report = {"mode": "lang", "source": str(src), "stats": stats(data), "sample_keys": list(data.keys())[:20]}
    else:
        quests = resolved.get("quests")
        if not quests:
            raise FileNotFoundError(f"Cannot locate ftbquests/quests under: {args.ftbquests}")
        report = scan_raw(Path(quests))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    src = find_default_source(args.ftbquests)
    source_data = load_lang(src)
    existing = None
    if args.existing and Path(args.existing).exists():
        existing = load_lang(Path(args.existing))
    out_data = merge_translation(source_data, existing, mode=args.mode)
    out_path = Path(args.out)
    fmt = args.format or out_path.suffix.lower().lstrip(".") or "snbt"
    save_lang(out_data, out_path, fmt=fmt)
    report = {"mode": "lang", "source": str(src), "out": str(out_path), "format": fmt, "stats": stats(source_data), "preserved_existing_keys": len(set(source_data) & set(existing or {})), "new_keys": len(set(source_data) - set(existing or {}))}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0



def cmd_export_raw(args: argparse.Namespace) -> int:
    resolved = resolve_paths(args.ftbquests)
    quests = resolved.get("quests")
    if not quests:
        raise FileNotFoundError(f"Cannot locate ftbquests/quests under: {args.ftbquests}")
    out_data = raw_key_template(Path(quests), mode=args.mode)
    existing = None
    if args.existing and Path(args.existing).exists():
        existing = load_lang(Path(args.existing))
        # Preserve existing translated values for matching keys.
        for k in list(out_data.keys()):
            if k in existing:
                out_data[k] = existing[k]
    out_path = Path(args.out)
    fmt = args.format or out_path.suffix.lower().lstrip(".") or "json"
    save_lang(out_data, out_path, fmt=fmt)
    report = {
        "mode": "raw-export",
        "quests_dir": str(quests),
        "out": str(out_path),
        "format": fmt,
        "keys": len(out_data),
        "preserved_existing_keys": len(set(out_data) & set(existing or {})),
        "new_keys": len(set(out_data) - set(existing or {})),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_compare_raw(args: argparse.Namespace) -> int:
    resolved = resolve_paths(args.ftbquests)
    quests = resolved.get("quests")
    if not quests:
        raise FileNotFoundError(f"Cannot locate ftbquests/quests under: {args.ftbquests}")
    raw_keys = set(raw_key_template(Path(quests)).keys())
    lang_data = load_lang(Path(args.lang))
    lang_keys = set(lang_data.keys())
    missing_in_lang = sorted(raw_keys - lang_keys)
    extra_in_lang = sorted(lang_keys - raw_keys)
    report = {
        "raw_keys": len(raw_keys),
        "lang_keys": len(lang_keys),
        "missing_in_lang": len(missing_in_lang),
        "extra_in_lang": len(extra_in_lang),
        "missing_sample": missing_in_lang[:50],
        "extra_sample": extra_in_lang[:50],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if missing_in_lang else 0


def cmd_merge_template(args: argparse.Namespace) -> int:
    """Fill a blank template with values from an existing lang/localizer file.

    This is useful after export-raw:
      template: keys generated by QLF, usually with empty values
      values:   Localizer output or an older translation file
      out:      merged file with matching values filled in and missing values blank
    """
    template_data = load_lang(Path(args.template))
    values_data = load_lang(Path(args.values))
    out: OrderedDict[str, Any] = OrderedDict()
    filled = 0
    missing = 0

    for key, template_value in template_data.items():
        if key in values_data:
            out[key] = values_data[key]
            filled += 1
        else:
            # Preserve template structure if it is an array, otherwise blank.
            out[key] = ["" for _ in template_value] if isinstance(template_value, list) else ""
            missing += 1

    extra = sorted(set(values_data) - set(template_data))
    out_path = Path(args.out)
    fmt = args.format or out_path.suffix.lower().lstrip(".") or "json"
    save_lang(out, out_path, fmt=fmt)

    report = {
        "template_keys": len(template_data),
        "values_keys": len(values_data),
        "filled": filled,
        "missing": missing,
        "extra_values_keys": len(extra),
        "extra_sample": extra[:50],
        "out": str(out_path),
        "format": fmt,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if missing else 0


def cmd_diff_lang(args: argparse.Namespace) -> int:
    """Compare two lang/json/snbt files by key and value."""
    old_data = load_lang(Path(args.old))
    new_data = load_lang(Path(args.new))

    old_keys = set(old_data)
    new_keys = set(new_data)
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    changed = sorted(k for k in (old_keys & new_keys) if old_data[k] != new_data[k])

    report = {
        "old_keys": len(old_data),
        "new_keys": len(new_data),
        "added": len(added),
        "removed": len(removed),
        "changed": len(changed),
        "added_sample": added[:50],
        "removed_sample": removed[:50],
        "changed_sample": changed[:50],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0



def cmd_resolve_text(args: argparse.Namespace) -> int:
    data, report = resolve_texts(args.path, locale=args.locale, raw_fallback=not args.no_raw_fallback)
    manifest = None
    if getattr(args, "manifest", None):
        manifest = build_manifest_for_resolved(args.path, args.locale, data, report)
        Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["manifest"] = str(Path(args.manifest))
        report["manifest_keys"] = len(manifest.get("keys", {}))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.out:
        out_path = Path(args.out)
        fmt = args.format or out_path.suffix.lower().lstrip(".") or "json"
        save_lang(data, out_path, fmt=fmt)
    return 0


def cmd_export_auto(args: argparse.Namespace) -> int:
    data, report = resolve_texts(args.path, locale=args.locale, raw_fallback=True)
    # Optional existing translation preservation.
    existing = None
    preserved = 0
    new_keys = len(data)
    if args.existing and Path(args.existing).exists():
        existing = load_lang(Path(args.existing))
        out: OrderedDict[str, Any] = OrderedDict()
        for k, v in data.items():
            if k in existing:
                out[k] = existing[k]
                preserved += 1
            else:
                if args.new_mode == "blank":
                    out[k] = ["" for _ in v] if isinstance(v, list) else ""
                elif args.new_mode == "copy-source":
                    out[k] = v
                else:
                    out[k] = v
        new_keys = len(set(data) - set(existing))
        data = out
    elif args.template_mode == "blank":
        data = blank_template(data, mode="blank")

    out_path = Path(args.out)
    fmt = args.format or out_path.suffix.lower().lstrip(".") or "json"
    save_lang(data, out_path, fmt=fmt)
    out_report = dict(report)
    out_report.update({
        "out": str(out_path),
        "format": fmt,
        "template_mode": args.template_mode,
        "preserved_existing_keys": preserved,
        "new_keys": new_keys,
    })
    print(json.dumps(out_report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(out_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    source_data = load_lang(Path(args.source))
    old_data = load_lang(Path(args.old))
    out_data = merge_translation(source_data, old_data, mode=args.mode)
    out_path = Path(args.out)
    fmt = args.format or out_path.suffix.lower().lstrip(".") or "snbt"
    save_lang(out_data, out_path, fmt=fmt)
    report = {"source_keys": len(source_data), "old_keys": len(old_data), "preserved": len(set(source_data) & set(old_data)), "added": len(set(source_data) - set(old_data)), "removed_from_old": len(set(old_data) - set(source_data)), "out": str(out_path)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _value_type_name(value: Any) -> str:
    if isinstance(value, list):
        return "list"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def _value_line_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 1


def validate_lang_pair(source_data: OrderedDict[str, Any], target_data: OrderedDict[str, Any], *,
                       source_diag: dict[str, Any] | None = None,
                       target_diag: dict[str, Any] | None = None,
                       allow_missing: bool = False,
                       allow_extra: bool = False,
                       fail_on_empty: bool = False,
                       allow_type_mismatch: bool = False,
                       forbid_unmapped: bool = True) -> tuple[dict[str, Any], int]:
    source_diag = source_diag or {}
    target_diag = target_diag or {}
    missing = [k for k in source_data if k not in target_data]
    extra = [k for k in target_data if k not in source_data]
    empty = []
    type_mismatch = []
    line_count_mismatch = []
    unmapped_keys = []

    for k, v in target_data.items():
        if _is_blank_value(v):
            empty.append(k)
        if forbid_unmapped and str(k).startswith("__unmapped__"):
            unmapped_keys.append(k)

    for k in source_data.keys() & target_data.keys():
        sv = source_data[k]
        tv = target_data[k]
        if _value_type_name(sv) != _value_type_name(tv):
            type_mismatch.append({"key": k, "source_type": _value_type_name(sv), "target_type": _value_type_name(tv)})
        elif isinstance(sv, list) and isinstance(tv, list) and len(sv) != len(tv):
            line_count_mismatch.append({"key": k, "source_lines": len(sv), "target_lines": len(tv)})

    errors: list[str] = []
    warnings: list[str] = []
    if missing and not allow_missing:
        errors.append("target is missing source keys")
    if extra and not allow_extra:
        warnings.append("target has extra keys not present in source; extra keys will be ignored during inject")
    if fail_on_empty and empty:
        errors.append("target contains empty values")
    elif empty:
        warnings.append("target contains empty values")
    if type_mismatch and not allow_type_mismatch:
        errors.append("target value types do not match source")
    if line_count_mismatch:
        warnings.append("some list values have different line counts")
    if target_diag.get("duplicate_keys"):
        errors.append("target contains duplicate keys")
    if source_diag.get("duplicate_keys"):
        warnings.append("source contains duplicate keys")
    if unmapped_keys:
        warnings.append("target contains __unmapped__ keys")

    report = {
        "source_keys": len(source_data),
        "target_keys": len(target_data),
        "missing_keys": len(missing),
        "extra_keys": len(extra),
        "empty_values": len(empty),
        "type_mismatches": len(type_mismatch),
        "line_count_mismatches": len(line_count_mismatch),
        "target_duplicate_keys": int(target_diag.get("duplicate_keys", 0)),
        "source_duplicate_keys": int(source_diag.get("duplicate_keys", 0)),
        "unmapped_keys": len(unmapped_keys),
        "missing_sample": missing[:50],
        "extra_sample": extra[:50],
        "empty_sample": empty[:50],
        "type_mismatch_sample": type_mismatch[:50],
        "line_count_mismatch_sample": line_count_mismatch[:50],
        "target_duplicate_sample": target_diag.get("duplicate_sample", [])[:50],
        "source_duplicate_sample": source_diag.get("duplicate_sample", [])[:50],
        "unmapped_sample": unmapped_keys[:50],
        "warnings": warnings,
        "errors": errors,
        "warning_count": len(warnings),
        "error_count": len(errors),
        "severity": {
            "missing_keys": "error",
            "extra_keys": "warning",
            "empty_values": "error" if fail_on_empty else "warning",
            "type_mismatches": "error",
            "line_count_mismatches": "warning",
            "target_duplicate_keys": "error",
            "source_duplicate_keys": "warning",
            "unmapped_keys": "warning",
        },
        "ok": not errors,
    }
    return report, (0 if not errors else 1)


def cmd_validate(args: argparse.Namespace) -> int:
    if not args.source and not args.manifest:
        raise ValueError("validate requires --source or --manifest")
    if not args.target:
        raise ValueError("validate requires --target")

    if args.manifest:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
        source_keys = OrderedDict()
        manifest_type_missing = 0
        for k, info in manifest.get("keys", {}).items():
            expected = info.get("value_type") if isinstance(info, dict) else None
            line_count = info.get("line_count", 1) if isinstance(info, dict) else 1
            if expected == "list":
                try:
                    n = max(0, int(line_count))
                except Exception:
                    n = 1
                source_keys[k] = [""] * n
            elif expected == "string":
                source_keys[k] = ""
            else:
                # Backward compatibility for v1.5-v1.8 manifests.
                # Without value_type, validate can still check keys, but type checks are unreliable.
                manifest_type_missing += 1
                source_keys[k] = ""
        source_diag = {"duplicate_keys": 0, "duplicate_sample": []}
        source_desc = {
            "mode": "manifest",
            "path": str(Path(args.manifest)),
            "keys": len(source_keys),
            "manifest_version": manifest.get("qlf_manifest_version"),
            "source_system": manifest.get("source_system"),
            "manifest_type_missing": manifest_type_missing,
        }
    else:
        source_keys, source_diag = load_lang_with_diagnostics(Path(args.source))
        source_desc = {"mode": "source", "path": str(Path(args.source)), "keys": len(source_keys)}

    target_data, target_diag = load_lang_with_diagnostics(Path(args.target))
    report, code = validate_lang_pair(
        source_keys,
        target_data,
        source_diag=source_diag,
        target_diag=target_diag,
        allow_missing=args.allow_missing,
        allow_extra=args.allow_extra,
        fail_on_empty=args.fail_on_empty,
        allow_type_mismatch=args.allow_type_mismatch,
        forbid_unmapped=not args.allow_unmapped,
    )
    report["source"] = source_desc
    if args.manifest and source_desc.get("manifest_type_missing"):
        report.setdefault("warnings", []).append("manifest does not contain value_type for some keys; type validation may be unreliable. Re-run resolve-text --manifest with v1.8.1 or later.")
    report["target"] = {"path": str(Path(args.target)), "keys": len(target_data)}
    report["strictness"] = {
        "allow_missing": args.allow_missing,
        "allow_extra": args.allow_extra,
        "fail_on_empty": args.fail_on_empty,
        "allow_type_mismatch": args.allow_type_mismatch,
        "allow_unmapped": args.allow_unmapped,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return code


def cmd_inject(args: argparse.Namespace) -> int:
    translation = load_lang(Path(args.translation))
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)

    if args.write_to_instance and args.out_dir:
        raise ValueError("Use either --out-dir for package mode or --write-to-instance for direct write mode, not both.")
    if args.write_to_instance:
        out_root = Path(args.write_to_instance)
        mode = "direct-write"
    elif args.out_dir:
        out_root = Path(args.out_dir)
        mode = "package"
    else:
        raise ValueError("inject requires either --out-dir or --write-to-instance")

    report = inject_from_manifest(
        translation,
        manifest,
        args.locale,
        out_root,
        strict=not args.no_strict,
        backup_existing=not args.no_backup,
    )
    report["inject_mode"] = mode
    report["output_root"] = str(out_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if report["missing_keys"] else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qlf", description="QLF v1.9.3 prototype with adapter SDK and examples")
    sub = p.add_subparsers(dest="cmd", required=True)

    so = sub.add_parser("sources", help="list registered QLF source adapters and optionally detect them in an instance")
    so.add_argument("--instance", help="Optional modpack instance folder to inspect")
    so.add_argument("--report", help="Optional JSON report path")
    so.set_defaults(func=cmd_sources)

    ad = sub.add_parser("adapters", help="list registered QLF adapters with SDK metadata")
    ad.add_argument("--report", help="Optional JSON report path")
    ad.set_defaults(func=cmd_adapters)

    ai = sub.add_parser("adapter-info", help="show SDK metadata for one QLF adapter")
    ai.add_argument("name", help="Adapter name, e.g. ftbquests")
    ai.add_argument("--report", help="Optional JSON report path")
    ai.set_defaults(func=cmd_adapter_info)

    at = sub.add_parser("adapter-template", help="write a starter adapter template file")
    at.add_argument("name", help="Adapter python identifier, e.g. patchouli or quest_kubejs")
    at.add_argument("--out", required=True, help="Output .py path for the template")
    at.add_argument("--force", action="store_true", help="Overwrite output if it already exists")
    at.add_argument("--report", help="Optional JSON report path")
    at.set_defaults(func=cmd_adapter_template)

    l = sub.add_parser("locate", help="show what QLF detects in a folder")
    l.add_argument("path", help="Instance folder, config/ftbquests, or ftbquests/quests")
    l.set_defaults(func=cmd_locate)

    s = sub.add_parser("scan", help="scan FTB Quests. Uses lang mode if en_us.snbt exists, else raw diagnostic mode")
    s.add_argument("--ftbquests", required=True, help="Path to instance folder, ftbquests, or ftbquests/quests")
    s.add_argument("--report", help="Optional JSON report path")
    s.set_defaults(func=cmd_scan)

    e = sub.add_parser("export", help="export translation template from en_us.snbt. Requires lang mode")
    e.add_argument("--ftbquests", required=True, help="Path to instance folder, ftbquests, or ftbquests/quests")
    e.add_argument("--out", required=True, help="Output file, e.g. zh_tw.snbt or zh_tw.json")
    e.add_argument("--format", choices=["snbt", "json"], help="Output format")
    e.add_argument("--existing", help="Existing translation to preserve by key")
    e.add_argument("--mode", choices=["blank", "copy-source"], default="blank", help="New key value mode")
    e.set_defaults(func=cmd_export)


    er = sub.add_parser("export-raw", help="export blank translation template from raw FTB Quests translation references")
    er.add_argument("--ftbquests", required=True, help="Path to instance folder, ftbquests, or ftbquests/quests")
    er.add_argument("--out", required=True, help="Output file, e.g. zh_tw_template.json or zh_tw.snbt")
    er.add_argument("--format", choices=["snbt", "json"], help="Output format")
    er.add_argument("--existing", help="Existing translation to preserve by key")
    er.add_argument("--mode", choices=["blank", "copy-key"], default="blank", help="New key value mode")
    er.set_defaults(func=cmd_export_raw)

    cr = sub.add_parser("compare-raw", help="compare raw FTB Quests translation references with an existing lang/json file")
    cr.add_argument("--ftbquests", required=True, help="Path to instance folder, ftbquests, or ftbquests/quests")
    cr.add_argument("--lang", required=True, help="Existing Localizer/lang file, snbt or json")
    cr.add_argument("--report", help="Optional JSON report path")
    cr.set_defaults(func=cmd_compare_raw)


    mt = sub.add_parser("merge-template", help="fill a blank template with values from an existing lang/localizer file")
    mt.add_argument("--template", required=True, help="Blank template generated by export-raw/export")
    mt.add_argument("--values", required=True, help="Existing lang/localizer file to copy values from")
    mt.add_argument("--out", required=True, help="Merged output file")
    mt.add_argument("--format", choices=["snbt", "json"], help="Output format")
    mt.add_argument("--report", help="Optional JSON report path")
    mt.set_defaults(func=cmd_merge_template)

    dl = sub.add_parser("diff-lang", help="compare two lang/json/snbt files by key and value")
    dl.add_argument("--old", required=True, help="Old lang file")
    dl.add_argument("--new", required=True, help="New lang file")
    dl.add_argument("--report", help="Optional JSON report path")
    dl.set_defaults(func=cmd_diff_lang)



    rt = sub.add_parser("resolve-text", help="resolve key -> source text using native lang, discovered lang files, or raw blank fallback")
    rt.add_argument("path", help="Instance folder, config/ftbquests, or ftbquests/quests")
    rt.add_argument("--locale", default="en_us", help="Locale to resolve, default en_us")
    rt.add_argument("--out", help="Optional output lang file, e.g. en_us_resolved.json")
    rt.add_argument("--format", choices=["snbt", "json"], help="Output format")
    rt.add_argument("--report", help="Optional JSON report path")
    rt.add_argument("--manifest", help="Optional manifest output path for later inject, e.g. manifest.json")
    rt.add_argument("--no-raw-fallback", action="store_true", help="Fail instead of outputting blank raw template when text cannot be resolved")
    rt.set_defaults(func=cmd_resolve_text)

    ea = sub.add_parser("export-auto", help="auto-export source text or template from any supported FTBQ pack layout")
    ea.add_argument("path", help="Instance folder, config/ftbquests, or ftbquests/quests")
    ea.add_argument("--out", required=True, help="Output file, e.g. en_us_resolved.json or zh_tw_template.json")
    ea.add_argument("--locale", default="en_us", help="Source locale to resolve, default en_us")
    ea.add_argument("--format", choices=["snbt", "json"], help="Output format")
    ea.add_argument("--existing", help="Existing translation to preserve by key")
    ea.add_argument("--template-mode", choices=["copy-source", "blank"], default="copy-source", help="Without --existing, output source text or blank template")
    ea.add_argument("--new-mode", choices=["copy-source", "blank"], default="blank", help="With --existing, value for newly added keys")
    ea.add_argument("--report", help="Optional JSON report path")
    ea.set_defaults(func=cmd_export_auto)



    au = sub.add_parser("audit", help="audit native FTBQ lang keys against raw quest/chapter indexes")
    au.add_argument("--ftbquests", required=True, help="Path to instance folder, ftbquests, or ftbquests/quests used to build ID map")
    au.add_argument("--input", required=True, help="Native FTBQ lang file, e.g. en_us_resolved.json")
    au.add_argument("--report", help="Optional JSON report path")
    au.set_defaults(func=cmd_audit)

    km = sub.add_parser("keymap", help="convert native FTBQ keys to FTB Quest Localizer-style keys")
    km.add_argument("--ftbquests", required=True, help="Path to instance folder, ftbquests, or ftbquests/quests used to build ID map")
    km.add_argument("--input", required=True, help="Native FTBQ lang file, e.g. en_us_resolved.json")
    km.add_argument("--out", required=True, help="Output Localizer-style lang file")
    km.add_argument("--format", choices=["snbt", "json"], help="Output format")
    km.add_argument("--report", help="Optional JSON report path")
    km.add_argument("--reference-localizer", help="Optional Localizer-style lang file used to infer unmapped IDs by unique text matching")
    km.add_argument("--keep-unmapped", action="store_true", help="Keep still-unmapped native keys as __unmapped__.<native_key> instead of dropping them")
    km.add_argument("--no-split-arrays", action="store_true", help="Do not split quest_desc arrays into description1/2/3")
    km.set_defaults(func=cmd_keymap)

    cm = sub.add_parser("compare-mapped", help="compare native FTBQ lang after Localizer-style key mapping with another Localizer-style lang file")
    cm.add_argument("--ftbquests", required=True, help="Path to instance folder, ftbquests, or ftbquests/quests used to build ID map")
    cm.add_argument("--native", required=True, help="Native FTBQ lang file, e.g. en_us_resolved.json")
    cm.add_argument("--other", required=True, help="Localizer-style lang file to compare with")
    cm.add_argument("--report", help="Optional JSON report path")
    cm.add_argument("--use-other-as-reference", action="store_true", help="Use --other to infer unmapped native IDs by unique text matching before comparison")
    cm.add_argument("--no-split-arrays", action="store_true", help="Do not split quest_desc arrays into description1/2/3")
    cm.set_defaults(func=cmd_compare_mapped)


    sy = sub.add_parser("sync", help="sync old translation against a new source language file")
    sy.add_argument("--source", required=True, help="New source lang file, usually en_us.snbt")
    sy.add_argument("--old", required=True, help="Old translation file, snbt or json")
    sy.add_argument("--out", required=True, help="Output synced translation")
    sy.add_argument("--format", choices=["snbt", "json"], help="Output format")
    sy.add_argument("--mode", choices=["blank", "copy-source"], default="blank", help="Value for newly added keys")
    sy.set_defaults(func=cmd_sync)

    ij = sub.add_parser("inject", help="inject translated JSON/SNBT using manifest.json. Supports package mode or direct write mode.")
    ij.add_argument("--translation", required=True, help="Translated file, e.g. zh_tw.json")
    ij.add_argument("--manifest", required=True, help="Manifest generated by resolve-text --manifest")
    ij.add_argument("--locale", default="zh_tw", help="Target locale, default zh_tw")
    ij.add_argument("--out-dir", help="Package output folder. Copy its contents into the modpack root after checking.")
    ij.add_argument("--write-to-instance", help="Direct write mode: write output files directly into the modpack instance folder")
    ij.add_argument("--report", help="Optional JSON report path")
    ij.add_argument("--no-strict", action="store_true", help="Allow missing/extra keys instead of aborting on mismatch")
    ij.add_argument("--no-backup", action="store_true", help="Do not create .bak backups when overwriting existing target files")
    ij.set_defaults(func=cmd_inject)


    dbg = sub.add_parser("debug", help="debug QLF paths, manifest, translation keys, and predicted inject outputs without writing files")
    dbg.add_argument("--instance", help="Modpack instance folder to inspect")
    dbg.add_argument("--manifest", help="manifest.json generated by resolve-text --manifest")
    dbg.add_argument("--translation", help="translated file to validate against manifest")
    dbg.add_argument("--locale", default="zh_tw", help="target locale used for predicted output paths")
    dbg.add_argument("--out-dir", help="package output folder for predicted paths")
    dbg.add_argument("--write-to-instance", help="direct write instance folder for predicted paths")
    dbg.add_argument("--no-backup", action="store_true", help="assume no backup will be created")
    dbg.add_argument("--report", help="Optional JSON report path")
    dbg.set_defaults(func=cmd_debug)

    df = sub.add_parser("diff", help="compare two lang/json/snbt files and optionally write added/removed/changed details")
    df.add_argument("--old", required=True, help="old/source lang file")
    df.add_argument("--new", required=True, help="new/translated lang file")
    df.add_argument("--report", help="Optional JSON report path")
    df.add_argument("--added-out", help="Optional JSON file containing added keys")
    df.add_argument("--removed-out", help="Optional JSON file containing removed keys")
    df.add_argument("--changed-out", help="Optional JSON file containing changed key values")
    df.add_argument("--sample-only", action="store_true", help="Only write sample rows to added/removed/changed output files")
    df.set_defaults(func=cmd_diff)


    v = sub.add_parser("validate", help="validate target translation keys against source or manifest")
    v.add_argument("--source", help="Source lang file, e.g. en_us.json")
    v.add_argument("--manifest", help="Manifest generated by resolve-text --manifest; validates target keys against manifest keys")
    v.add_argument("--target", required=True, help="Target translated file, e.g. zh_tw.json")
    v.add_argument("--report", help="Optional JSON report path")
    v.add_argument("--allow-missing", action="store_true", help="Do not fail when target is missing keys")
    v.add_argument("--allow-extra", action="store_true", help="Do not fail when target has extra keys")
    v.add_argument("--fail-on-empty", action="store_true", help="Fail when target contains blank values")
    v.add_argument("--allow-type-mismatch", action="store_true", help="Do not fail when source and target value types differ")
    v.add_argument("--allow-unmapped", action="store_true", help="Do not warn about __unmapped__ keys")
    v.set_defaults(func=cmd_validate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
