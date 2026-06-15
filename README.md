# Quest Logistics Framework (QLF)

**Quest Logistics Framework** — 任務物流框架。

QLF extracts quest-related text, lets you translate it externally, validates the translated file, and injects it back to the correct source location.

QLF does **not** translate text by itself.

QLF 負責的是物流，而不是翻譯本身。

```text
Read → Merge → Validate → Deliver
```

---

# What is QLF? / QLF 是什麼？

QLF is a framework for handling Minecraft modpack quest translation workflows.

QLF 是一套用於 Minecraft 整合包任務翻譯流程的框架。

It allows translators to:

* Extract quest text from modpacks
* Translate using any workflow
* Validate translation completeness
* Inject translations back into the correct files

它允許翻譯者：

* 從整合包匯出任務文字
* 使用任意翻譯流程進行翻譯
* 驗證翻譯完整性
* 自動回填到正確的檔案位置

---

# Core Philosophy / 核心理念

```text
Many Sources
↓
One Translation File
↓
Many Sources
```

QLF separates translation work from source file formats.

QLF 將翻譯工作與原始檔格式分離。

Translators should focus on translation.

The framework handles extraction, validation, tracking, and delivery.

翻譯者專注於翻譯內容。

QLF 負責匯出、驗證、追蹤與回填。

---

# Current Status / 目前狀態

Core workflow is fully working for FTB Quests native language files.

目前已完整支援 FTB Quests 原生語言檔流程。

```text
FTB Quests
↓
resolve-text
↓
translation file + manifest
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

---

# Important Non-Goal / 非目標範圍

QLF is quest-focused.

QLF 專注於任務內容。

QLF does NOT handle:

* mods/*.jar language files
* General mod localization
* Item names
* Block names
* Entity names
* General Minecraft language packs

QLF 不處理：

* mods/*.jar 語言檔
* 一般模組翻譯
* 物品名稱
* 方塊名稱
* 生物名稱
* 一般 Minecraft 語言包

Those belong to a future MLF-style workflow.

上述內容屬於未來的 MLF（Mod Logistics Framework）範疇。

---

# Quick Start / 快速開始

## Step 1 — Extract / 匯出任務文字

Generate a translation file and manifest.

產生翻譯檔與 manifest。

```powershell
python qlf.py resolve-text "<modpack instance>" --out en_us.json --manifest manifest.json --report resolve_report.json
```

Generated files / 產生檔案：

```text
en_us.json
manifest.json
```

---

## Step 2 — Translate / 翻譯

Translate the exported JSON using any workflow.

使用任意翻譯流程翻譯匯出的 JSON。

Examples / 例如：

* Human Translation
* ChatGPT
* Codex
* DeepL
* Existing Team Workflow

Output example / 輸出範例：

```text
zh_tw.json
```

---

## Step 3 — Validate / 驗證翻譯

Validate translation completeness before injection.

回填前驗證翻譯完整性。

```powershell
python qlf.py validate --manifest manifest.json --target zh_tw.json --report validate_report.json
```

Expected result / 預期結果：

```json
{
  "ok": true
}
```

---

## Step 4 — Inject / 回填翻譯

Inject translated content back into the modpack.

將翻譯內容回填至整合包。

```powershell
python qlf.py inject --translation zh_tw.json --manifest manifest.json --locale zh_tw --write-to-instance "<modpack instance>" --report inject_report.json
```

Generated file / 產生檔案：

```text
localized quest file
```

Examples / 範例：

```text
zh_tw.snbt
ja_jp.snbt
ko_kr.snbt
fr_fr.snbt
en_gb.snbt
```

---

## Package Mode / 封裝模式

Instead of writing directly into the modpack, QLF can generate a deployable package.

QLF 可以輸出封裝好的翻譯包，而不直接修改整合包。

```powershell
python qlf.py inject --translation zh_tw.json --manifest manifest.json --locale zh_tw --out-dir qlf_package --report inject_report.json
```

---

## Step 5 — Launch Minecraft / 啟動遊戲

Launch Minecraft and switch to the target language.

啟動 Minecraft 並切換至目標語言。

The translated quest content should now appear in-game.

翻譯後的任務內容即會顯示於遊戲中。

---

# Adapter SDK

QLF v1.9+ introduces an adapter system.

QLF v1.9 起引入 Adapter 架構。

FTB Quests is the first official adapter.

FTB Quests 為第一個正式 Adapter。

List registered adapters:

列出已註冊 Adapter：

```powershell
python qlf.py adapters
```

Show adapter information:

顯示 Adapter 資訊：

```powershell
python qlf.py adapter-info ftbquests
```

Detect available sources:

偵測可用來源：

```powershell
python qlf.py sources --instance "<modpack instance>"
```

---

# Adapter Developer Kit (ADK)

QLF v1.9.3 introduces adapter development tools.

QLF v1.9.3 新增 Adapter 開發工具。

Generate an adapter template:

產生 Adapter 範本：

```powershell
python qlf.py adapter-template patchouli --out qlf_core\adapters\patchouli.py
```

Included files:

```text
docs/SDK_EXAMPLE.md
docs/ADAPTER_TEMPLATE.md
templates/adapter_template.py
qlf_core/adapters/example_adapter.py
```

The example adapter is not registered by default.

範例 Adapter 預設不會自動註冊。

---

# Documentation

Additional documentation can be found in:

更多文件請參閱：

* docs/QUICKSTART.md
* docs/ARCHITECTURE.md
* docs/SDK.md
* docs/MANIFEST.md
* docs/SCOPE.md
* docs/ROADMAP.md
* docs/HISTORY.md

---

# Safety

QLF only reads and writes local files.

QLF 僅讀寫本機檔案。

It does not require:

不需要：

* Minecraft runtime
* Launcher-specific support
* Localizer mod
* AI API key
* Internet access

When direct-write mode overwrites an existing file, QLF automatically creates a backup.

使用 Direct Write 模式覆寫既有檔案時，QLF 會自動建立備份：

```text
*.bak
```

---

# Current Release

```text
v1.9.3 — Adapter Developer Kit
```

Current capabilities:

目前功能：

* Quest Extraction
* Manifest Tracking
* Validation
* Diff
* Direct Write Injection
* Adapter SDK
* Adapter Templates
* Documentation

---

# Future Roadmap

Planned features:

未來規劃：

* Interactive Text UI
* Desktop GUI
* Additional Quest Adapters
* Patchouli Support
* Quest-related KubeJS Support
* Translation Memory
* MLF (Mod Logistics Framework)

```

Many Sources
↓
One Translation File
↓
Many Sources
```
