# green-ai

Tools and plugins that make the environmental cost of AI visible. Currently supports **Claude Code** and **Google Antigravity (agy)**.

## Quick Install

### Claude Code

```text
/plugin marketplace add leon-lourenco/green-ai
/plugin install <plugin>@green-ai
```

### Google Antigravity (agy)

Workspace hooks (`.agents/hooks.json`), skills (`.agents/skills/`), or run directly:

```bash
./plugins/friendly-reminder/scripts/friendly-reminder-agy --text
./plugins/virtual-garden/scripts/virtual-garden-agy --full
```

## Plugins

| Plugin | What it does |
|---|---|
| [friendly-reminder](plugins/friendly-reminder) | After every response, shows the water it took, pictured as something everyday, plus energy, tokens, API cost and quota, with daily and monthly totals. Works in Claude Code and Google Antigravity (`agy`). |
| [virtual-garden](plugins/virtual-garden) | A mindful ASCII garden above the prompt that grows with green AI habits: sun for prompt caching, fresh soil for a lean context and `/compact`, four species to unlock. Works in Claude Code and Google Antigravity (`agy`). |

## Layout

```
.claude-plugin/marketplace.json   catalog of Claude Code plugins
.agents/                          Antigravity workspace hooks, skills and rules
plugins/<name>/                   one plugin per folder
  .claude-plugin/plugin.json      Claude Code manifest
  src/<package>/                  shared Python engine
    adapters/                     agent adapters (agy, claude, etc.)
  skills/ hooks/ scripts/ ...     agent components
```

To add a plugin, create its folder under `plugins/`, add an entry to `marketplace.json`, and run `claude plugin validate .`.
