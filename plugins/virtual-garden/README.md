# Virtual Garden 🌱

A mindful ASCII garden that grows with the habits that make AI cheaper to run: a well-used prompt cache, a lean context, and `/compact` when the conversation grows. It rewards and never scolds: a careless turn only slows the plant down.

After each response in Claude Code, a band above the prompt shows one line:

```
🎍 Bonsai · Young plant (Lv 4/6) · 120/800 XP · ☀️ 92% · 🪴 Soil 81%
```

**View garden** opens the whole thing:

```
┌──────────────────────────────────────────────┐
│ 🎍 Bonsai · Young plant               Lv 4/6 │
├──────────────────────────────────────────────┤
│                   .-~~~-.                    │
│                  ( ~ ~ ~ )                   │
│                   '-.|.-'.-.                 │
│                      |__(~ )                 │
│                      |   '-'                 │
│                      |                       │
│                  \=======/                   │
│                   \_____/                    │
├──────────────────────────────────────────────┤
│ Growth [██░░░░░░░░░░░░] 120/800 XP           │
│ ☀️ Sun 92%   🪴 Soil 81%   Turns 57          │
│ Garden 🎍 4/6  🌵 1/6  🔒  🔒                │
│ Badges ✂️ Pruner                             │
├──────────────────────────────────────────────┤
│ 💡 Ask for the change, not the whole file    │
│    back: fewer output tokens, less energy.   │
└──────────────────────────────────────────────┘
```

It speaks English and Portuguese, works in Claude Code and Google Antigravity (`agy`), and both tend the same garden. It needs only `python3` 3.8+ and has no dependencies.

## Install

### Claude Code

```text
/plugin marketplace add leon-lourenco/green-ai
/plugin install virtual-garden@green-ai
```

The band has three buttons: **View garden** / **Collapse** switches between the line and the full garden, **Options** picks the format, plant and language, and **Hide** hides it for the session. The same settings are in `/config`. You can also ask Claude to show your garden or to switch plants: the plugin's `garden` skill runs the script for you.

### Google Antigravity (`agy`)

Register the hook once, from the plugin folder:

```bash
./scripts/virtual-garden-agy --install-hook
```

This adds a `Stop` hook with the script's absolute path to `~/.gemini/config/hooks.json`, keeping any hooks already there. Inside this repository, `.agents/hooks.json` does the same for the workspace. After each turn, the hook grows the garden without adding anything to the conversation. Antigravity hooks can't show text, so to see the garden, run:

```bash
./scripts/virtual-garden-agy --text    # one line
./scripts/virtual-garden-agy --full    # the whole garden
./scripts/virtual-garden-agy --switch cactus
```

A manual run also applies your latest agy turn, if the hook hasn't already. Pass `--transcript <path>` for a specific conversation. Inside this repository, the workspace skill `.agents/skills/virtual-garden` lets the agent run it for you.

## How it grows

Every answered turn earns XP. One turn counts once, however many times the band is redrawn or the script is run.

| | What feeds it | Why it matters |
|---|---|---|
| ☀️ **Sun** | Prompt caching. Sun rises when 75%+ of the prompt was read from cache and dims below 40%. | A cached prompt costs a fraction of the compute of a fresh one. |
| 🪴 **Soil** | Context size. It dries past 40k tokens, faster past 80k and 120k, and recovers below 40k. `/compact` or a new session renews it. | Every call re-reads the whole context. |
| 🌱 **XP** | 10 per turn, +5 to +20 for the cache, +5 for a context under 40k, +30 for a `/compact` you ran yourself. | |

While sun or soil is below 40%, the plant grows at half speed 🐌. A break of an hour or more restores some sun. The first turn of a session is not judged on cache, since nothing is cached yet.

### Stages

Seed (0 XP) → Sprout (100) → Sapling (300) → Young plant (700) → Blooming (1,500) → Majestic (3,000).

### Collection

Each species keeps its own growth, so switching plants never loses any.

| | Species | Unlocked by |
|---|---|---|
| 🎍 | Bonsai | from the start |
| 🌵 | Cactus (Mandacaru) | growing any plant to Sapling |
| 🌸 | Sakura (Cerejeira) | 5 turns in a row with the cache at 75%+ |
| 🌼 | Golden Ipê (Ipê-amarelo) | a manual `/compact`, or 10 turns in a row under 40k tokens of context |

Pick one in **Options**, in `/config` (`species`), or with `--switch`. A locked pick tells you how to unlock it. With `species` left at `current`, the plant you switched to stays.

### Badges

✂️ Pruner (a manual `/compact`) · ☀️ Sunny (the 5-turn cache streak) · 🍃 Light (the 10-turn lean streak) · 🏆 Master (a plant reaches Majestic) · 🧺 Collector (every species unlocked).

## Settings

| Setting | Values | Default |
|---|---|---|
| `format` | `short` (one line), `full` (the whole garden), `off` (keeps growing, shows nothing) | `short` |
| `species` | `current`, `bonsai`, `cactus`, `sakura`, `ipe` | `current` |
| `language` | `auto` (Claude Code's `language` setting, then the locale), `en`, `pt` | `auto` |

The agy script reads the same settings from `CLAUDE_PLUGIN_OPTION_FORMAT`, `CLAUDE_PLUGIN_OPTION_SPECIES` and `CLAUDE_PLUGIN_OPTION_LANGUAGE`.

## How it works

### In Claude Code

1. After each response, the mod (`hooks/register.tsx`) runs `scripts/virtual-garden` with the Stop payload.
2. It reads the session transcript, waiting up to 3 s for the last response to be written, and measures the last answered turn: tokens read from cache, fresh and written, and the context size of its last call. A `compact_boundary` line since the previous turn means the context was compacted, by you (`manual`) or automatically.
3. It applies the turn to the garden under a lock, keyed by session and prompt id, and returns both views. The band draws the one the format asks for.

### In Google Antigravity (`agy`)

1. The `Stop` hook, or a manual run, starts `scripts/virtual-garden-agy` (`adapters/agy.py`).
2. It reads `~/.gemini/*/brain/<conversation>/.system_generated/logs/transcript.jsonl` and sums `input_tokens`, `cache_read_tokens` and `output_tokens` of the `PLANNER_RESPONSE` steps since the last prompt the model answered.
3. It applies the turn keyed by the conversation folder and the prompt's step, so the hook and a manual run never count it twice, and answers `{"decision": "allow"}` so the agent stops as usual. agy writes no compaction marker, so its soil renews with a new conversation.

### The garden file

`garden-state.json` in `~/.claude/plugins/data/virtual-garden-green-ai/`, or in `VIRTUAL_GARDEN_DATA` or `CLAUDE_PLUGIN_DATA` when set. A 0.1.0 garden is read and carried over. Errors are logged to `error.log` in the same folder; the hook never interrupts a session.

## License

MIT
