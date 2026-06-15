# QLF Scope

QLF stands for **Quest Logistics Framework**.

It is designed to move quest-related text through a translation workflow.

## QLF handles

- FTB Quests native lang files
- Quest titles
- Quest subtitles
- Quest descriptions
- Chapter titles
- Chapter subtitles
- Quest-related text from future pack-authored sources

## QLF does not handle

- General mod language files
- `mods/*.jar`
- Item names
- Block names
- Entity names
- General JEI/tooltips
- Full mod localization

## Why this boundary exists

Quest translation and mod translation are different workflows.

QLF answers:

```text
What should the player do next?
```

MLF, if it exists later, would answer:

```text
What is this item/block/entity called?
```

Keeping these separate prevents QLF output from becoming a huge mixed translation file that contains both quest text and general mod text.
