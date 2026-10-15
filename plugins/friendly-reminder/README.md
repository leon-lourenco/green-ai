# Friendly Reminder 💧

Every answer from an AI model costs water: the water that cools the data center, plus the water used to generate its electricity. Friendly Reminder is a Claude Code plugin that makes that cost visible. After each response, it shows two lines in a band above the prompt:

```
💧 56 mL of water in this response (29% of a small glass) · today 1.4 L · month 19 L (≈ 1.9 buckets)
⚡ 15 Wh · 1.3M tokens · $0.82
```

- **Water** leads the message. It is an estimate built from published research, pictured as something everyday (see [Comparisons](#comparisons)), and totaled for the day and the month across all your Claude Code sessions.
- **Energy** is estimated the same way.
- **Tokens** are exact: the API's own counts for every request in the turn, subagents included.
- **API cost** is exact at Anthropic's list prices, with cache writes and reads priced separately. On a subscription, this is the API-equivalent value of the work, not what you pay.
- **Quota**: on Pro, Max and Team, your 5-hour and weekly usage. The short format shows it once either reaches 50%.

It speaks English by default, with Portuguese one click away. It detects your billing mode and plan by itself. It needs only `python3` 3.8+ and has no dependencies.

## Install

```text
/plugin marketplace add leon-lourenco/green-ai
/plugin install friendly-reminder@green-ai
```

The reminder appears after your next response. On Windows, make sure `python3` is on `PATH`.

To update later, run `/plugin marketplace update green-ai`, then `/reload-plugins` (or start a new session).

## The band

The band appears when a response ends and hides while Claude is working. It has two buttons:

- **Options** opens pickers for format, language, comparison, estimate and water scope. A pick is saved to `/config` and the reminder of the last response redraws at once, so you see the change without waiting for the next one. **Done** closes the pickers.
- **Hide** dismisses the band for the rest of the session. The history keeps recording.

Click a button, or press `ctrl+x tab` to focus the band from the keyboard: Enter acts, the arrow keys move through a picker's choices, and Esc returns to the prompt.

## Formats

**short** (default) is the two lines above.

**table** adds a title, a plain sentence, the day and month comparisons, a turn/month table and, once there is more than one month of history, a month-by-month table:

```
💧 Friendly Reminder · turn 7 · opus-5-5
This response used ≈ 55.6 mL of water, 29% of a small glass.
Today: ≈ 1.40 L (≈ 7.4 small glasses) · Month: ≈ 19.0 L (≈ 1.9 buckets)
┌──────────┬───────────┬────────────┐
│          │      Turn │      Month │
├──────────┼───────────┼────────────┤
│ Water    │ ≈ 55.6 mL │   ≈ 19.0 L │
│ Energy   │ ≈ 15.4 Wh │ ≈ 5.20 kWh │
│ Tokens   │ 1,291,395 │      40.9M │
│ API cost │    $0.818 │     $52.40 │
└──────────┴───────────┴────────────┘
┌──────────┬──────────┬────────────┬────────┬──────────┐
│ By month │    Water │     Energy │ Tokens │ API cost │
├──────────┼──────────┼────────────┼────────┼──────────┤
│ Oct 2026 │ ≈ 19.0 L │ ≈ 5.20 kWh │  40.9M │   $52.40 │
│ Sep 2026 │ ≈ 31.2 L │ ≈ 8.60 kWh │  66.0M │   $87.10 │
└──────────┴──────────┴────────────┴────────┴──────────┘
Max quota: 5h 34% · week 58%
```

**detailed** is the table plus the token breakdown (input, cache writes, cache reads, output) and the low–high range of the water and energy estimates:

```
Water: 3.40 mL – 410 mL
Energy: 2.10 Wh – 64.0 Wh
≈ = estimate (central profile; water counts data-center cooling + power generation).
```

**off** shows nothing but keeps recording the history, so the totals are right when you turn it back on.

## Comparisons

Milliliters are hard to picture, so each amount is compared with something familiar. Two modes:

- **progressive** (default) grows with your use. The short format shows it on the month, where the total keeps climbing. How far it goes is for you to find out.
- **random** pictures each response as something different, and usually something fun:

  ```
  💧 56 mL of water in this response (22% of a cactus watering) · today 1.4 L · month 19 L
  ```

  The pick is fixed for each response, so redrawing the band from **Options** doesn't change it.

The comparisons live in [`comparisons.py`](src/friendly_reminder/comparisons.py). Ideas are welcome.

## Configure

Use **Options** on the band, or open `/config` and edit the **Friendly Reminder** rows. You can also run `claude plugin configure friendly-reminder@green-ai` from your shell. Currency and exchange rate are only in `/config`.

| Option | Values | Default |
|---|---|---|
| `format` | `short`, `table`, `detailed`, `off` (see [Formats](#formats)) | `short` |
| `language` | `en`, `pt`, `auto` (Claude Code's language setting, then the system locale) | `en` |
| `comparison` | `progressive` (grows with your use), `random` (something different every response) | `progressive` |
| `currency` + `exchange_rate` | any currency code, and units of it per 1 USD (e.g. `BRL`, `5.4`) | `USD`, `1` |
| `footprint_profile` | `central`, `low`, `high`: which end of the published range to show | `central` |
| `water_scope` | `full` (cooling + power generation), `onsite` (cooling only) | `full` |

### Data and overrides

Everything the plugin keeps is in its data directory, `~/.claude/plugins/data/friendly-reminder-green-ai/`:

- `history/YYYY-MM.jsonl` holds one line per response: tokens, cost, energy, water and models. The day, month and month-by-month totals come from here. Delete a file to reset that month (sessions still on disk are counted again after the next response).
- `sync-state.json` remembers which transcripts were already read. Delete it to read them all again.
- `error.log` collects any error, so a failure never interrupts your session.
- `pricing.json` (optional) adds or replaces model prices, using the same shape as [`data/pricing.json`](data/pricing.json).
- `footprint.json` (optional) replaces water and energy factors, using the same shape as [`data/footprint.json`](data/footprint.json).

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

Friendly Reminder is a mod: a plugin whose hooks module (`hooks/register.tsx`) draws in Claude Code's interface. When Claude finishes a response:

1. The module runs `scripts/friendly-reminder`, passing it the turn's `Stop` payload and your settings.
2. The script reads the session transcript and the subagent transcripts beside it.
3. It sums the `usage` of every API call since the turn's opening prompt, prices it, and estimates energy and water.
4. It records the turn in the history, keyed by session and turn, so measuring the same turn twice never counts it twice.
5. It reads the other transcripts in `~/.claude/projects` that changed since its last run and records any turn the history lacks: other sessions and windows, sessions started before the plugin was installed, turns interrupted with Esc. Only transcripts touched since the start of last month are read, and a run stops after 6 seconds and continues after the next response, so the first one after installing can take a few responses to catch up.
6. The day, month and month-by-month totals come from the history.
7. The module draws the result above the prompt.

A pick in **Options** writes the `/config` row, then runs step 1 again for the last response with the new setting.

The plugin never reads credentials. Billing detection looks only at provider switches, at whether an API key is present, and at the plan type in `~/.claude.json`.

## Troubleshooting

- **No band after a response.** Check that the plugin is enabled (`/plugin`) and that `python3` runs from your shell. If you pressed **Hide**, the band stays hidden until the next session. If you updated the plugin with `/reload-plugins` and the band stopped, start a new session (`claude --continue` keeps the conversation).
- **Numbers look off.** Look at `error.log` in the data directory. Prices are a snapshot, so a new model may be missing from `data/pricing.json` (the cost then shows a `*`).
- **Wrong language.** The default is English. Pick `pt` or `auto` in **Options**.

## Limits

- Water and energy are estimates with a wide range. Tokens and API cost are exact.
- Prices are a snapshot (`as_of` in `data/pricing.json`). Bedrock and Vertex use partner pricing, which can differ.
- Quota comes from an undocumented cache in `~/.claude.json`, so it is only as fresh as Claude Code's last fetch. Subscriptions have 5-hour and weekly limits, not a monthly allowance.
- A turn interrupted with Esc doesn't fire `Stop`. It enters the totals after the next response, when the transcripts are read again.
- The history only goes back as far as the transcripts Claude Code keeps (30 days by default, `cleanupPeriodDays`) and to the start of last month.
- The response's own numbers are read the moment it ends, so once in a while they miss the last request. The totals fix that after the next response.
- Mods are an early-access Claude Code feature, and their API may change between releases.
- Where an organization manages Claude Code, it runs `Stop` hooks only for plugins listed in managed settings, so the band stays empty.
- The Claude mobile app shows the band without **Options**, since it can't draw pickers yet.

## Development

```bash
python3 -m unittest discover -s tests     # Python: no dependencies
claude plugin test .                       # the mod: tests/*.test.tsx
claude plugin validate .
claude --plugin-dir .                      # try it without installing
```

## License

MIT
