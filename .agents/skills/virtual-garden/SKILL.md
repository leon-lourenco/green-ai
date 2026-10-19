---
name: virtual-garden
description: >-
  Shows the Virtual Garden: the plant's growth stage, sunlight (prompt caching), soil (context size),
  collection, badges and a gardener tip, or switches the plant being tended. Use this skill when the user
  asks about their garden, plant, bonsai, collection or badges, or asks for green AI gamification stats.
---

# Virtual Garden 🌱

Run these from the repository root. To show the full garden (it also applies the latest turn, once):

```bash
./plugins/virtual-garden/scripts/virtual-garden-agy --full
```

Use `--text` for the one-line summary. Show the output to the user as is, in a code block.

To tend another unlocked species (`bonsai`, `cactus`, `sakura`, `ipe`). Each one keeps its own growth:

```bash
./plugins/virtual-garden/scripts/virtual-garden-agy --switch sakura
```

## Portuguese Language

```bash
CLAUDE_PLUGIN_OPTION_LANGUAGE=pt ./plugins/virtual-garden/scripts/virtual-garden-agy --full
```
