# Changelog

## 1.2.1 - 2026-10-18

- agy: the hook now runs on `Stop`, once per turn, and adds nothing to the conversation. `PostInvocation` ran after every model call and put the reminder into the agent's context. Antigravity hooks can't show text, so `--text` (or the workspace skill) shows the reminder.
- agy: `--install-hook` registers the hook in `~/.gemini/config/hooks.json` by absolute path, keeping other hooks. Copying `.agents/hooks.json` there didn't work outside this repository.
- agy: every conversation was recorded under the same session (`.system_generated`), so turns of different conversations overwrote each other in the history. The session is now the conversation folder's id.
- agy: prompts that got no answer are skipped, so a manual run shows the last answered turn instead of nothing.
- agy: the model comes from the hook payload or, on a manual run, from `~/.gemini/antigravity-cli/settings.json`, since transcripts don't record it.
- agy: `--text` no longer reads stdin, which hung when an agent's shell left the pipe open.
- Gemini prices from the Gemini API pricing page (2026-10-16). 1.2.0 had the 2.0 Flash price on every Flash model and half the 2.5 Pro output price; 2.5 Pro and 3.1 Pro now have their long-context tier.
- The data folder is always Claude Code's (or `GREEN_AI_DATA`), so the history no longer splits when agy was installed first.

## 1.2.0 - 2026-10-17

- Added Google Antigravity (`agy`) adapter: parse Antigravity's JSONL transcripts and run Friendly Reminder via lifecycle hooks (`PostInvocation`), workspace skills, or CLI (`scripts/friendly-reminder-agy`).
- Expanded pricing to include Google Gemini models (`gemini-3.8-flash`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-1.5-flash`, `gemini-1.5-pro`) and OpenAI models (`gpt-4o`, `gpt-4o-mini`).
- Multi-agent data persistence: unified data directory fallback supporting both `~/.claude/` and `~/.gemini/` as well as `GREEN_AI_DATA`.

## 1.1.0 - 2026-10-15

- Day and month totals now count every Claude Code session, not only the responses the band measured. After each response the plugin reads the transcripts that changed and records what the history is missing: other sessions and windows, sessions started before the plugin was installed, turns interrupted with Esc, and turns whose numbers were read before the last request reached the disk.
- **table** and **detailed** show a month-by-month table once there is more than one month of history.
- A turn recorded in one month's file and again in the next counts once.

## 1.0.0 - 2026-10-15

First stable release.

- **Options** button on the band. It opens pickers for format, language, comparison, estimate (central/low/high) and water scope. A pick saves to `/config` and redraws the last response's reminder right away. Currency and exchange rate stay in `/config`.
- New `comparison` option: **progressive** (default) grows with your use; **random** pictures each response as something different. The fixed 250 mL glass is gone.
- English is now the default language. `auto` still follows Claude Code's language setting, then the system locale.

## 0.2.0 - 2026-10-15

- The reminder is now a band above the prompt, drawn by a mod (`hooks/register.tsx`), instead of a `Stop` hook `systemMessage`. No more `Stop says:` before every line. The band hides while Claude works, and **Hide** dismisses it for the session.
- Cleaner short format: rounded numbers (`12 mL`, `1,4 L`, `326 mil tokens`, `US$ 0,20`), no `≈` on every value, quota only once it reaches 50%, and no "numbers may be low" warning line.

## 0.1.0 - 2026-10-15

- First release. A `Stop` hook shows the turn's estimated water use first, as a share of a 250 mL glass, with day and month totals. Energy, exact tokens, API cost and subscription quota follow.
- Formats: short (default, two lines), table, detailed (token breakdown and low–high range), off (history only).
- Auto-detects billing mode (subscription plan, API, Bedrock, Vertex, Foundry) and language (en, pt).
