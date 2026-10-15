# green-ai

A Claude Code plugin marketplace of tools that make the environmental cost of AI visible. Each plugin lives in `plugins/<name>/` and installs on its own.

```text
/plugin marketplace add leon-lourenco/green-ai
/plugin install <plugin>@green-ai
```

| Plugin | What it does |
|---|---|
| [friendly-reminder](plugins/friendly-reminder) | After every response, a band above the prompt shows the water it took, pictured as something everyday, plus energy, tokens, API cost and quota, with daily and monthly totals. Settings are one click away in the band. |

## Layout

```
.claude-plugin/marketplace.json   catalog of plugins
plugins/<name>/                   one plugin per folder
  .claude-plugin/plugin.json      manifest
  skills/ hooks/ scripts/ ...     components
```

To add a plugin, create its folder under `plugins/`, add an entry to `marketplace.json`, and run `claude plugin validate .`.
