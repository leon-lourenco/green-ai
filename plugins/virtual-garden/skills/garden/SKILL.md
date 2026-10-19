---
name: garden
description: >-
  Shows the Virtual Garden: the plant's growth stage, sunlight (prompt caching), soil (context size),
  collection, badges and a gardener tip, or switches the plant being tended. Use when the user asks
  about their garden, plant, bonsai, collection or badges, or wants to tend another species.
---

# Virtual Garden 🌱

Show the full garden (it reads the shared garden file and never changes it):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/virtual-garden" --full
```

Use `--text` for the one-line summary. Show the output to the user as is, in a code block.

To tend another unlocked species (`bonsai`, `cactus`, `sakura`, `ipe`). Each one keeps its own growth:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/virtual-garden" --switch sakura
```

A locked species answers with how to unlock it. The `species` setting in `/config` overrides a switch on the next response unless it is `current`.

How the garden grows:

- **Sun** rises with prompt caching (75%+ of the prompt read from cache) and dims below 40%.
- **Soil** dries as the context grows past 40k tokens; `/compact` or a new session renews it.
- The plant grows on every answered turn, at half speed while sun or soil is below 40%.
