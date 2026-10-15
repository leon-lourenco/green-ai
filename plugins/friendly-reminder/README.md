# Friendly Reminder 💧

Every answer from an AI model costs water: the water that cools the data center, plus the water used to generate its electricity. Friendly Reminder is a Claude Code plugin that makes that cost visible. After each response, it adds two lines:

```
💧 ≈ 113 mL of water in this response (45% of a glass) · today ≈ 1.42 L · month ≈ 18.6 L
⚡ ≈ 31.4 Wh · 2,064,412 tokens · $1.35 · Pro quota: 5h 38%, week 21%
```

Prefer a table? Set `format` to `table`, or to `detailed` to also see the token breakdown and the low–high estimate range.

- **Water** leads the message. It is an estimate (marked `≈`) built from published research, compared with a 250 mL glass, and totaled for the day and the month.
- **Energy** is estimated the same way.
- **Tokens** are exact: the API's own counts for every request in the turn, subagents included.
- **API cost** is exact at Anthropic's list prices, with cache writes and reads priced separately. On a subscription, this is the API-equivalent value of the work, not what you pay.
- **Quota**: on Pro, Max and Team, your 5-hour and weekly usage.

It configures itself (billing mode, plan, language) and needs only `python3` 3.8+. No dependencies.

## Install

```text
/plugin marketplace add leon-lourenco/green-ai
/plugin install friendly-reminder@green-ai
```

The reminder appears after your next response. On Windows, make sure `python3` is on `PATH`.

## Configure

Open `/config` and edit the **Friendly Reminder** rows, or run `claude plugin configure friendly-reminder@green-ai` from your shell.

| Option | Values | Default |
|---|---|---|
| `format` | `short` (two lines); `table` (turn/month table); `detailed` (table plus token breakdown and the low–high range); `off` (show nothing, keep history) | `short` |
| `language` | `auto`, `en`, `pt` | `auto` |
| `currency` + `exchange_rate` | any code, units per 1 USD | `USD`, `1` |
| `footprint_profile` | `central`, `low`, `high` | `central` |
| `water_scope` | `full` (cooling + power generation), `onsite` (cooling only) | `full` |

Optional overrides go in the plugin data directory, `~/.claude/plugins/data/friendly-reminder-green-ai/`:

- `pricing.json` adds or replaces model prices, using the same shape as [`data/pricing.json`](data/pricing.json).
- `footprint.json` replaces water and energy factors.

## How the water is estimated

Anthropic doesn't publish per-token energy or water figures, so Friendly Reminder estimates them:

```
energy (Wh) = PUE × Σ tokens_by_class × Wh_per_token(class)
water (mL)  = energy × (on-site cooling WUE + off-site water intensity of electricity)   [L/kWh]
```

| Factor | low | central | high |
|---|---|---|---|
| Output, Wh per 1k tokens | 0.1 | 0.5 | 2.0 |
| Uncached input and cache writes, Wh per 1k | 0.005 | 0.05 | 0.4 |
| Cache reads, Wh per 1k | 0.0005 | 0.005 | 0.04 |
| PUE | 1.08 | 1.12 | 1.2 |
| On-site cooling, L/kWh | 0.2 | 0.5 | 1.8 |
| Power generation, L/kWh | 1.0 | 3.1 | 4.5 |

A few things drive these factors:

- Output (decode) tokens dominate inference energy, and cache reads are the cheapest tokens. Claude Code re-reads its context from cache on every tool call, so a busy turn can reach millions of cache-read tokens.
- With `water_scope=onsite`, the estimate counts cooling only. Most vendor per-prompt figures report that, and they come out much lower.
- The `detailed` format shows the low–high range for every turn.

Sources and assumptions are listed in [`data/footprint.json`](data/footprint.json). Corrections backed by better sources are very welcome.

## How it works

A `Stop` hook runs `scripts/friendly-reminder` when Claude finishes a response:

1. It reads the session transcript and the subagent transcripts beside it.
2. It sums the `usage` of every API call since the turn's opening prompt, prices it, and estimates energy and water.
3. It appends the turn to `history/YYYY-MM.jsonl` in the plugin data directory, from which it computes the day and month totals.
4. It returns the message as a `systemMessage`.

The plugin never reads credentials. Billing detection looks only at provider switches, at whether an API key is present, and at the plan type in `~/.claude.json`. Errors go to `error.log` in the data directory, and the session continues normally.

## Limits

- Water and energy are estimates with a wide range. Tokens and API cost are exact.
- Prices are a snapshot (`as_of` in `data/pricing.json`). Bedrock and Vertex use partner pricing, which can differ.
- Quota comes from an undocumented cache in `~/.claude.json`, so it is only as fresh as Claude Code's last fetch. Subscriptions have 5-hour and weekly limits, not a monthly allowance.
- A turn interrupted with Esc doesn't fire `Stop`, so it is missing from the history.
- Claude Code prefixes each line of a hook message with `Stop says:`.

## Development

```bash
python3 -m unittest discover -s tests     # no dependencies
claude plugin validate .
claude --plugin-dir .                      # try it without installing
```

## License

MIT
