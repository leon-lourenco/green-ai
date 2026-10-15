# Changelog

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
