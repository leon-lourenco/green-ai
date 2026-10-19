# Changelog

## 1.0.0 - 2026-10-18

- A turn counts once. The band's "View garden" button and every manual agy run used to apply the latest turn again, so the plant grew twice. Turns are now keyed by session and prompt.
- Soil follows the context size of the turn's last call. It used to sum every call of the turn, so any turn with tool calls looked like 120k+ tokens.
- Cache written in a turn counts as uncached, and the first turn of a session isn't judged on cache.
- `/compact` is detected from the transcript's `compact_boundary` line. Only a manual compaction earns the bonus and the Pruner badge; an automatic one still renews the soil.
- The plant grows at half speed while sun or soil is below 40%, and an hour's break restores some sun.
- Each species keeps its own growth. New species: 🌼 Golden Ipê (Ipê-amarelo), unlocked by a manual `/compact` or 10 lean turns. New badges: Light, Collector.
- The band shows the turn's news: level ups, unlocks, badges, and how to unlock a species you picked. Options picks the format, plant and language; View garden switches views without running Python again.
- Tips are about whatever the garden needs most: soil, sun, or a general one.
- The box is measured in terminal columns, so emoji no longer push the right border out, and tips wrap between words. Every label is translated; 0.1.0 mixed Portuguese labels with English values.
- Two sessions finishing a turn at once no longer lose each other's growth: the garden file is written under a lock.
- agy: the hook runs on `Stop`, adds nothing to the conversation and answers `{"decision": "allow"}`; `--install-hook` registers it by absolute path; manual runs never read stdin.
- The `format` setting is `short`, `full` or `off` (0.1.0's `ascii` is now `full`). `species` defaults to `current`. Claude Code gets a `garden` skill.
- A 0.1.0 garden file is carried over.

## 0.1.0 - 2026-10-17

- Initial release of Virtual Garden.
- Positive eco-gamification engine tracking XP, vitality (sunlight/cache), and soil health (context compactness).
- Botanical collection: Bonsai Zen, Cherry Blossom / Ipê Rosa, Desert Cactus.
- 6 growth stages with ASCII art rendering.
- Dual-platform support: Claude Code interactive band mod and Google Antigravity (`agy`) adapter and CLI.
