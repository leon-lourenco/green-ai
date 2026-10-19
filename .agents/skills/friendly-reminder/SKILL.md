---
name: friendly-reminder
description: >-
  Displays the environmental footprint (water in mL/L, energy in Wh/kWh, tokens and API cost)
  for the current conversation or latest AI response. Use this skill when the user asks about
  environmental impact, water used, energy consumed, tokens, carbon footprint, or asks for a green AI recap.
---

# Friendly Reminder 💧

Every answer from an AI model costs water: the water that cools the data center, plus the water used to generate its electricity. Friendly Reminder makes that cost visible.

## Quick Check

Run these from the repository root. To inspect the environmental cost of the last answered turn:

```bash
./plugins/friendly-reminder/scripts/friendly-reminder-agy --text
```

## Formats

To view in table or detailed format:

```bash
CLAUDE_PLUGIN_OPTION_FORMAT=table ./plugins/friendly-reminder/scripts/friendly-reminder-agy --text
```

```bash
CLAUDE_PLUGIN_OPTION_FORMAT=detailed ./plugins/friendly-reminder/scripts/friendly-reminder-agy --text
```

## Portuguese Language

```bash
CLAUDE_PLUGIN_OPTION_LANGUAGE=pt ./plugins/friendly-reminder/scripts/friendly-reminder-agy --text
```
