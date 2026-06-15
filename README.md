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

# Project Motivation / 開發動機

QLF started from a simple frustration:

Minecraft quest translation workflows often depend on launching the game, maintaining specific mod loaders, or relying on version-sensitive localization tools.

QLF began as an attempt to remove those dependencies and move the entire translation workflow outside Minecraft.

QLF 的起點其實很單純：

Minecraft 任務翻譯流程往往需要啟動遊戲、依賴特定 Loader，或使用容易受到版本影響的在地化工具。

QLF 的目標是將整個翻譯流程搬到遊戲之外完成。

```text
Extract
↓
Translate
↓
Validate
↓
Inject
```

No Minecraft runtime required.

不需要啟動 Minecraft。

No Localizer dependency required.

不需要依賴 Localizer。

No launcher-specific workflow required.

不需要依賴特定啟動器。

The goal is to make quest translation reproducible, maintainable, and automation-friendly.

目標是讓任務翻譯流程更容易維護、更容易自動化，也更容易團隊協作。

---

# Who Needs QLF? / 誰適合使用 QLF？

| Role                   | Pain Point                                                    | What QLF Provides                                                             |
| ---------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Translator             | Too many files, difficult paths, repetitive manual work       | One translation file, automated export and injection                          |
| Modpack Author         | Translation files are easy to break or distribute incorrectly | Manifest validation and structured delivery                                   |
| Server Owner           | Pack updates constantly invalidate existing translations      | Diff and Sync workflows preserve previous work                                |
| Localization Team Lead | Difficult collaboration and translation management            | Single-file workflow suitable for Crowdin, GitHub, or AI-assisted translation |

| 身份    | 常見痛點             | QLF 提供的幫助                           |
| ----- | ---------------- | ----------------------------------- |
| 漢化者   | 路徑複雜、檔案分散、手動回填麻煩 | 單一翻譯檔、自動匯出與回填                       |
| 整合包作者 | 翻譯檔容易損壞或回填錯誤     | Manifest 驗證與安全交付                    |
| 伺服器主  | 版本更新後翻譯容易失效      | Diff 與 Sync 協助保留既有成果                |
| 漢化組長  | 多人協作與版本管理困難      | 單一翻譯檔流程，適合 Crowdin、GitHub 或 AI 協作翻譯 |

---

# License / 授權條款

QLF is released under the MIT License.

QLF 採用 MIT License 授權。

You are free to:

你可以自由：

* Use / 使用
* Modify / 修改
* Distribute / 散布
* Integrate into other projects / 整合至其他專案

as long as the original license notice is retained.

但需保留原始授權聲明。

See the LICENSE file for details.

詳細內容請參閱 LICENSE 檔案。


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
