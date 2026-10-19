# Virtual Garden — Architecture

This document is for people changing the plugin. For what it does and how to use it, see the [README](../README.md).

- [Design principles](#design-principles)
- [Top level](#top-level)
- [Repository layout](#repository-layout)
- [Module dependencies](#module-dependencies)
- [Claude Code: one response](#claude-code-one-response)
- [Claude Code: the band](#claude-code-the-band)
- [Google Antigravity](#google-antigravity)
- [Measuring a turn](#measuring-a-turn)
- [Growing the garden](#growing-the-garden)
- [Data model](#data-model)
- [Counting a turn once](#counting-a-turn-once)
- [Rendering](#rendering)
- [Testing](#testing)

## Design principles

| Principle | What it means in the code |
|---|---|
| **Never disrupt a session** | Every entry point catches all errors, logs them to `error.log` and exits 0. The band's TypeScript swallows failures too. |
| **Zero dependencies** | Python standard library only, 3.8+. The mod uses only the Claude Code mod API. |
| **One garden, many tools** | Claude Code, agy and manual runs share one state file, written under a lock. |
| **A turn counts once** | Each turn has a stable key; applying it again is a no-op that returns the same news. |
| **Reward, never punish** | Bad turns slow growth (halved XP, floors on sun and soil); nothing decreases XP or kills the plant. |
| **Pure core, thin edges** | `engine` and `render` are pure functions of the state; I/O lives in `transcript`, `state` and the entry points. |

## Top level

Who talks to whom. The Python package does all the measuring and drawing. The TypeScript mod only stores what Python returns and shows it. The mod passes the Stop payload on stdin and the options as `CLAUDE_PLUGIN_OPTION_*` variables; Python answers on stdout with both views (`summary`, `full`).

```mermaid
flowchart TB
    subgraph CC["Claude Code"]
        direction TB
        SESSION["Session"] -->|"writes"| TRANSCRIPT[("session transcript<br/>~/.claude/projects/…/*.jsonl")]
        SESSION -->|"Stop event"| MOD["Mod<br/>hooks/register.tsx"]
        MOD -->|"draws"| BAND["Band above the prompt"]
        CONFIG["/config · plugin options"] -->|"options"| MOD
        SKILL["garden skill<br/>skills/garden"]
    end

    subgraph AG["Google Antigravity (agy)"]
        AGSESSION["Conversation"] -->|"writes"| AGTRANSCRIPT[("transcript.jsonl<br/>~/.gemini/…/brain/<id>/…")]
        AGSESSION -->|"Stop hook"| AGHOOK["scripts/virtual-garden-agy"]
        AGSKILL["workspace skill<br/>.agents/skills/virtual-garden"]
    end

    subgraph PY["Python package · src/virtual_garden"]
        CLAUDE_EP["hook.py<br/>(scripts/virtual-garden)"]
        AGY_EP["adapters/agy.py"]
        CORE["engine · render · tips · species"]
        STORE["state.py"]
    end

    STATE[("garden-state.json<br/>+ lock · error.log")]

    MOD -->|"Stop payload + options"| CLAUDE_EP
    CLAUDE_EP -->|"both views"| MOD
    SKILL -->|"--full / --switch"| CLAUDE_EP
    AGHOOK --> AGY_EP
    AGSKILL -->|"--full / --switch"| AGY_EP
    CLAUDE_EP -->|"reads"| TRANSCRIPT
    AGY_EP -->|"reads"| AGTRANSCRIPT
    CLAUDE_EP & AGY_EP --> CORE
    CLAUDE_EP & AGY_EP --> STORE
    STORE <-->|"locked read-modify-write"| STATE
```

## Repository layout

```
plugins/virtual-garden/
├── .claude-plugin/plugin.json    manifest: name, version, userConfig (format, species, language)
├── hooks/
│   ├── hooks.json                registers the mod module
│   └── register.tsx              the band: Stop handler + AbovePrompt renderer
├── types/index.d.ts              the mod's state atoms (GardenView, view, …)
├── skills/garden/SKILL.md        lets Claude show or switch the garden
├── scripts/
│   ├── virtual-garden            launcher → virtual_garden.hook.main
│   └── virtual-garden-agy        launcher → virtual_garden.adapters.agy.main
├── src/virtual_garden/
│   ├── hook.py                   Claude Code entry point (Stop payload or manual flags)
│   ├── adapters/agy.py           Antigravity entry point, transcript parser, --install-hook
│   ├── cli.py                    shared by both: output views, manual commands, error log
│   ├── transcript.py             Claude Code transcript → (turn key, TurnMetrics)
│   ├── state.py                  garden file: load, atomic save, lock, record_turn
│   ├── engine.py                 the rules: XP, sun, soil, unlocks, badges
│   ├── render.py                 summary line, full box, news, terminal widths
│   ├── tips.py                   tip picked by what the garden needs
│   ├── species.py                catalog: names, icons, stage names, ASCII sprites
│   ├── models.py                 TurnMetrics, Event, GardenState (+ 0.1.0 migration)
│   └── config.py                 settings, language detection, data folder
├── tests/                        unittest suites (no third-party runner needed)
└── docs/ARCHITECTURE.md          this file
```

Outside the plugin folder, the repository adds `.claude-plugin/marketplace.json` (the Claude Code catalog) and `.agents/` (agy workspace hook, skill and rule).

## Module dependencies

Arrows point from a module to what it imports. The graph has no cycles. `species` and `models` are the foundation, `engine` and `render` are pure logic, and only the top row does I/O.

```mermaid
flowchart TB
    hook["hook.py"]
    agy["adapters/agy.py"]
    cli["cli.py"]
    transcript["transcript.py"]
    state["state.py"]
    render["render.py"]
    tips["tips.py"]
    engine["engine.py"]
    config["config.py"]
    models["models.py"]
    species["species.py"]

    hook --> cli & config & state & transcript
    agy --> cli & config & state & models
    cli --> config & engine & models & render & species & state
    transcript --> models
    state --> engine & models
    render --> engine & models & species & tips
    tips --> models
    engine --> models & species
    config --> species
    models --> species

    classDef entry fill:#e8f1ff,stroke:#4a78c2
    classDef io fill:#fff4e0,stroke:#c28a2c
    classDef pure fill:#e9f7ec,stroke:#3d8f55
    class hook,agy entry
    class cli,transcript,state,config io
    class render,tips,engine,models,species pure
```

| Layer | Modules | May do I/O |
|---|---|---|
| Entry points | `hook`, `adapters/agy` | stdin, stdout, transcripts |
| Shared edges | `cli`, `transcript`, `state`, `config` | files, environment |
| Pure core | `engine`, `render`, `tips`, `models`, `species` | no |

## Claude Code: one response

What happens between the model finishing a response and the band changing. The Python process is short-lived: it starts, measures, saves and exits on every response.

```mermaid
sequenceDiagram
    autonumber
    participant CC as Claude Code
    participant Mod as register.tsx
    participant Py as hook.py
    participant Tr as transcript.py
    participant St as state.py
    participant Eng as engine.py
    participant Rd as render.py
    participant File as garden-state.json

    CC->>Mod: classic.Stop(payload)
    Mod->>Mod: save payload in lastStop
    Mod->>Py: python3 scripts/virtual-garden<br/>stdin = payload, env = options
    Py->>Tr: load_when_flushed(transcript, last message, 3 s)
    loop until the final response is on disk (max 3 s)
        Tr->>Tr: read JSONL, check stop_reason / last text
    end
    Py->>Tr: last_turn(entries)
    Tr-->>Py: key = prompt uuid, TurnMetrics
    Py->>St: record_turn("claude:session:key", metrics, species)
    St->>File: flock + read
    alt key already in seen_turns
        St-->>Py: state, replayed events
    else new turn
        St->>Eng: grow(state, metrics)
        Eng-->>St: events (level up, unlock, badge)
        St->>File: atomic write + unlock
        St-->>Py: state, events
    end
    Py->>Rd: render_summary + render_full (+ tip)
    Py-->>Mod: stdout {summary[], full[], systemMessage?, language}
    Mod->>Mod: save in last
    CC->>Mod: ui.render(AbovePrompt)
    Mod-->>CC: the band
```

## Claude Code: the band

The band's state lives in mod atoms (`types/index.d.ts`). Switching views never runs Python, because both views arrive in every response. Changing a setting runs Python again with the saved Stop payload, which is safe because the turn is already recorded.

```mermaid
stateDiagram-v2
    [*] --> Empty: no response yet
    Empty --> Summary: Stop · format short
    Empty --> Full: Stop · format full
    Empty --> Silent: Stop · format off
    Summary --> Full: View garden
    Full --> Summary: Collapse
    Summary --> Editing: Options
    Full --> Editing: Options
    Silent --> Editing: Options (panel kept open)
    Editing --> Summary: Done
    Editing --> Editing: pick → config.set → re-run Python with lastStop
    Summary --> Hidden: Hide
    Full --> Hidden: Hide
    Hidden --> [*]: session ends
```

| Atom | Holds |
|---|---|
| `last` | the last `GardenView` (`summary`, `full`, `language`) |
| `lastStop` | the last Stop payload, to redraw after a setting changes |
| `view` | `summary`, `full`, or `null` to follow the `format` setting |
| `isEditing` | the Options panel is open |
| `isHidden` | Hide was pressed this session |

## Google Antigravity

agy hooks can't show text and must let the agent stop, so the hook only records the turn. The user sees the garden from a manual run, which applies the latest turn too, in case the hook isn't installed. Both use the same key, so the turn counts once.

```mermaid
sequenceDiagram
    autonumber
    participant AG as agy
    participant Hook as virtual-garden-agy (hook)
    participant User as You / workspace skill
    participant Man as virtual-garden-agy --full
    participant St as state.py

    AG->>Hook: Stop · stdin {transcriptPath, …}
    Hook->>Hook: parse_agy_turn → key = step_index
    Hook->>St: record_turn("agy:conversation:step", metrics)
    Hook-->>AG: {"decision": "allow"}
    Note over AG,Hook: nothing is added to the conversation

    User->>Man: run (stdin is never read)
    Man->>Man: newest transcript.jsonl → same key
    Man->>St: record_turn (already seen → no change)
    Man-->>User: the full garden
```

## Measuring a turn

Both transcripts become the same `TurnMetrics`. Only the parsing differs.

```mermaid
flowchart TB
    subgraph Claude["Claude Code transcript"]
        C1["user lines that open a turn<br/>(not tool results, meta, compact summaries)"] --> C2["keep turns that got an assistant call"]
        C2 --> C3["last such turn"]
        C3 --> C4["de-duplicate calls by message.id<br/>(one call spans several lines)"]
        C4 --> C5["sum input · cache_read · cache_creation · output"]
        C4 --> C6["context = prompt size of the last call"]
        C3 --> C7["compact_boundary since the previous turn?<br/>trigger manual / auto"]
        C2 --> C8["only one answered turn → fresh session"]
    end

    subgraph Agy["agy transcript"]
        A1["USER_INPUT steps open turns"] --> A2["keep turns with PLANNER_RESPONSE steps"]
        A2 --> A3["last such turn"]
        A3 --> A4["sum input_tokens · cache_read_tokens · output_tokens"]
        A3 --> A5["context = input + cache_read of the last step"]
        A2 --> A6["only one answered turn → fresh session"]
    end

    C5 & C6 & C7 & C8 --> M["TurnMetrics"]
    A4 & A5 & A6 --> M
    M --> R["cache_ratio = cache_read / (input + cache_read + cache_write)"]
```

## Growing the garden

`engine.grow(state, turn)` applies one turn in place and returns the events to celebrate. The constants are at the top of `engine.py`.

```mermaid
flowchart TB
    START([turn]) --> REST{"an hour or more<br/>since the last turn?"}
    REST -->|yes| R1["sun +10"] --> FRESH
    REST -->|no| FRESH{"fresh session?"}
    FRESH -->|yes| F1["+5 XP · sun unchanged"]
    FRESH -->|no| CACHE["cache tier → XP bonus and sun change<br/>streak +1 if ratio ≥ 75%, else 0"]
    F1 & CACHE --> COMPACT{"compaction or<br/>fresh session?"}
    COMPACT -->|yes| S1["soil = 100"]
    S1 --> MANUAL{"manual /compact?"}
    MANUAL -->|yes| S2["+30 XP · ✂️ Pruner"]
    MANUAL -->|no| LEAN
    S2 --> LEAN
    COMPACT -->|no| SOIL["soil tier by context size<br/>(dries toward a floor, or +3)"] --> LEAN
    LEAN{"context under 40k?"} -->|yes| L1["+5 XP · lean streak +1"]
    LEAN -->|no| L2["lean streak = 0"]
    L1 & L2 --> SLOW{"sun or soil under 40%?"}
    SLOW -->|yes| HALF["XP ÷ 2"] --> ADD
    SLOW -->|no| ADD["add XP to the current species"]
    ADD --> EVENTS["level up? · streak badges?<br/>Master? · unlock rules? · Collector?"]
    EVENTS --> DONE([events])
```

Unlock rules (`engine.unlock_rule_met`) are checked after every turn, so a species unlocks on the turn its condition first holds.

## Data model

```mermaid
classDiagram
    class GardenState {
        species: str
        plants: Dict~str,int~
        unlocked: List~str~
        vitality: int
        soil: int
        turns: int
        cache_streak: int
        lean_streak: int
        badges: List~str~
        last_turn_at: str
        seen_turns: List~str~
        last_events: List~dict~
        xp() int
        to_dict() dict
        from_dict(data) GardenState
    }
    class TurnMetrics {
        input_tokens: int
        cache_read_tokens: int
        cache_write_tokens: int
        output_tokens: int
        context_tokens: int
        compaction: str | None
        fresh_session: bool
        timestamp: str
        prompt_tokens() int
        cache_ratio() float
    }
    class Event {
        kind: level_up | unlock | badge
        value: str
        species: str
    }
    class Settings {
        format: short | full | off
        species: current | bonsai | cactus | sakura | ipe
        language: auto | en | pt
    }
    TurnMetrics ..> GardenState : grow() updates
    GardenState "1" o-- "*" Event : last_events
    Settings ..> GardenState : species pick
```

`garden-state.json` is `GardenState.to_dict()` plus `"version": 1`. A file without `version` is a 0.1.0 garden and goes through `models._from_v0` (one XP pool → `plants`, renamed fields and badges). Unknown species are dropped and the current plant falls back to the bonsai, so a hand-edited or future file can't break the hook.

## Counting a turn once

Every entry point derives the same key for the same turn:

| Source | Key |
|---|---|
| Claude Code | `claude:<session_id>:<prompt uuid>` |
| agy | `agy:<conversation folder id>:<USER_INPUT step_index>` |

`state.record_turn` keeps the last 500 keys in `seen_turns`:

- **A new key:** the turn is applied, and its events are saved in `last_events`.
- **The latest key again** (a band redraw, a settings change): nothing is applied, and the saved events come back, so the news stays on screen.
- **An older key:** nothing is applied, and no events come back.

All of it happens inside `state.editing`, which holds an exclusive `fcntl.flock` on `garden-state.lock` from the read to the atomic replace (temp file + `os.replace`). On Windows there is no lock, but the write is still atomic.

## Rendering

- `render_summary` and `render_full` are pure: same state, language and seed, same lines. The tip seed is `session:turn`, so a redraw shows the same tip.
- Widths are terminal columns (`render.width`): East Asian wide characters and emoji count 2, a narrow symbol followed by U+FE0F (☀️, ✂️) counts 2, and combining marks and ZWJ count 0. Code points U+1F000–U+1FAFF count 2 even when Python 3.8's Unicode tables don't know them (🪴).
- The box is `INNER` = 46 columns wide. Text wraps between words (`wrap`), and badges wrap without splitting one (`wrap_items`).
- A sprite is drawn as one block, padded to its widest line and centered as a whole. The pot is shifted under the trunk (`species._trunk_column`), so stages wider than the pot stay upright.
- Every user-facing word is in `WORDS`, `BADGE_LABELS`, `UNLOCK_HINTS`, `species.NAMES` and `species.STAGE_NAMES`, in `en` and `pt`.

## Testing

```bash
python3 -m unittest discover -s tests     # from the plugin root
ruff check src tests
```

| Suite | Covers |
|---|---|
| `test_engine.py` | stage thresholds, every sun and soil tier and floor, fresh sessions, manual vs auto compaction, slow growth, rest, unlocks, badges, per-species growth |
| `test_render.py` | terminal widths, wrapping, every sprite fitting the box, **every line of every box the same width** for all species, stages and languages, no English in `pt` |
| `test_state.py` | round trip, broken files, 0.1.0 migration, a turn counting once, event replay, species picks |
| `test_transcript.py` | call de-duplication, context from the last call, unanswered prompts, compaction detection, flush wait |
| `test_entry_points.py` | the Claude hook end to end (formats, idempotency, error log), manual runs never reading stdin, `--switch`, the agy hook answer, `--install-hook` |

The suites run on Python 3.8 and on current versions. The mod (`register.tsx`) has no automated tests; `claude plugin validate` checks its hooks and state atoms.
