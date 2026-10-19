"""Draw the garden: a one-line summary, or the full garden in a box.

Widths are measured in terminal columns, not characters: an emoji takes two,
a variation selector none. Every line of the box comes out the same width.
"""

from __future__ import annotations

import unicodedata
from typing import Dict, List, Optional

from .engine import SLOW_BELOW, stage_for_xp, stage_progress, unlock_rule_met
from .models import Event, GardenState
from .species import ICONS, SPECIES, STAGES, species_name, sprite, stage_name
from .tips import pick_tip

INNER = 46  # columns between the side borders
BAR = 14

WORDS: Dict[str, Dict[str, str]] = {
    "en": {
        "level": "Lv {n}/{max}",
        "growth": "Growth",
        "sun": "Sun",
        "soil": "Soil",
        "turns": "Turns",
        "garden": "Garden",
        "badges": "Badges",
        "slow": "growing slowly: sun or soil under {n}%",
        "level_up": "🎉 Your {species} grew into a {stage}!",
        "unlock": "{icon} New species unlocked: {species}. Pick it in Options.",
        "badge": "🏅 Badge earned: {badge}",
        "locked": "🔒 {species} is still locked: {hint}",
    },
    "pt": {
        "level": "Nv {n}/{max}",
        "growth": "Progresso",
        "sun": "Sol",
        "soil": "Solo",
        "turns": "Turnos",
        "garden": "Jardim",
        "badges": "Medalhas",
        "slow": "crescimento lento: sol ou solo abaixo de {n}%",
        "level_up": "🎉 Sua planta ({species}) chegou a {stage}!",
        "unlock": "{icon} Nova espécie: {species}. Escolha em Opções.",
        "badge": "🏅 Medalha conquistada: {badge}",
        "locked": "🔒 {species} ainda está bloqueada: {hint}",
    },
}

BADGE_LABELS: Dict[str, Dict[str, str]] = {
    "en": {
        "pruner": "✂️ Pruner",
        "sunny": "☀️ Sunny",
        "light": "🍃 Light",
        "master": "🏆 Master",
        "collector": "🧺 Collector",
    },
    "pt": {
        "pruner": "✂️ Podador",
        "sunny": "☀️ Ensolarado",
        "light": "🍃 Leveza",
        "master": "🏆 Mestre",
        "collector": "🧺 Colecionador",
    },
}

UNLOCK_HINTS: Dict[str, Dict[str, str]] = {
    "en": {
        "cactus": "grow any plant to Sapling (Lv 3).",
        "sakura": "keep the cache at 75%+ for 5 turns in a row.",
        "ipe": "prune with /compact, or keep the context under 40k tokens for 10 turns.",
    },
    "pt": {
        "cactus": "leve qualquer planta a Muda (Nv 3).",
        "sakura": "mantenha o cache em 75%+ por 5 turnos seguidos.",
        "ipe": "pode com /compact, ou mantenha o contexto abaixo de 40k tokens por 10 turnos.",
    },
}


def _words(lang: str) -> Dict[str, str]:
    return WORDS.get(lang, WORDS["en"])


def char_width(ch: str) -> int:
    if ch in ("︎", "️", "‍") or unicodedata.combining(ch):
        return 0
    # Emoji newer than Python's Unicode tables report as narrow; they are wide.
    if unicodedata.east_asian_width(ch) in ("W", "F") or 0x1F000 <= ord(ch) <= 0x1FAFF:
        return 2
    return 1


def width(text: str) -> int:
    total = 0
    for i, ch in enumerate(text):
        # A narrow symbol followed by the emoji selector is drawn as a wide emoji.
        if ch == "️" and i and char_width(text[i - 1]) == 1:
            total += 1
        total += char_width(ch)
    return total


def pad(text: str, columns: int) -> str:
    return text + " " * max(columns - width(text), 0)


def wrap(text: str, columns: int, indent: str = "") -> List[str]:
    """Break on spaces; a word longer than a line goes on a line of its own."""
    lines: List[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if line and width(candidate) > columns:
            lines.append(line)
            line = indent + word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def wrap_items(items: List[str], columns: int, sep: str = "  ") -> List[str]:
    """Like ``wrap``, but never splits an item."""
    lines: List[str] = []
    for item in items:
        if lines and width(lines[-1] + sep + item) <= columns:
            lines[-1] += sep + item
        else:
            lines.append(item)
    return lines


def event_line(event: Event, lang: str) -> str:
    w = _words(lang)
    if event.kind == "level_up":
        return w["level_up"].format(species=species_name(event.species, lang), stage=stage_name(int(event.value), lang))
    if event.kind == "unlock":
        return w["unlock"].format(icon=ICONS.get(event.value, "🌱"), species=species_name(event.value, lang))
    return w["badge"].format(badge=BADGE_LABELS.get(lang, BADGE_LABELS["en"]).get(event.value, event.value))


def locked_line(species: str, lang: str) -> str:
    hint = UNLOCK_HINTS.get(lang, UNLOCK_HINTS["en"]).get(species, "")
    return _words(lang)["locked"].format(species=species_name(species, lang), hint=hint)


def _level(state: GardenState, lang: str) -> str:
    return _words(lang)["level"].format(n=stage_for_xp(state.xp), max=STAGES)


def _progress(xp: int) -> str:
    earned, needed = stage_progress(xp)
    if needed is None:
        return f"{xp} XP"
    return f"{earned}/{needed} XP"


def render_summary(state: GardenState, lang: str, notes: Optional[List[str]] = None) -> List[str]:
    """One line about the plant, then one line per thing that just happened."""
    w = _words(lang)
    stage = stage_for_xp(state.xp)
    head = (
        f"{ICONS[state.species]} {species_name(state.species, lang)} · {stage_name(stage, lang)} "
        f"({_level(state, lang)}) · {_progress(state.xp)} · ☀️ {state.vitality}% · 🪴 {w['soil']} {state.soil}%"
    )
    return [head] + list(notes or [])


def render_full(state: GardenState, lang: str, notes: Optional[List[str]] = None, seed: str = "") -> List[str]:
    """The garden in a box: the plant, its stats, the collection, news and a tip."""
    w = _words(lang)
    rule = "─" * INNER

    def row(text: str = "") -> str:
        return f"│ {pad(text, INNER - 2)} │"

    stage = stage_for_xp(state.xp)
    title = f"{ICONS[state.species]} {species_name(state.species, lang)} · {stage_name(stage, lang)}"
    level = _level(state, lang)
    gap = max(INNER - 2 - width(title) - width(level), 1)
    lines = [f"┌{rule}┐", row(title + " " * gap + level), f"├{rule}┤"]

    art = sprite(state.species, stage)
    art_width = max(width(line) for line in art)
    left = (INNER - art_width) // 2
    for line in art:
        lines.append("│" + pad(" " * left + line, INNER) + "│")
    lines.append(f"├{rule}┤")

    label = max(len(w[k]) for k in ("growth", "garden", "badges")) + 1
    earned, needed = stage_progress(state.xp)
    filled = BAR if needed is None else min(BAR, earned * BAR // max(needed, 1))
    lines.append(row(f"{w['growth']:<{label}}[{'█' * filled}{'░' * (BAR - filled)}] {_progress(state.xp)}"))
    lines.append(row(f"☀️ {w['sun']} {state.vitality}%   🪴 {w['soil']} {state.soil}%   {w['turns']} {state.turns}"))
    if min(state.vitality, state.soil) < SLOW_BELOW:
        lines.extend(row(text) for text in wrap(f"🐌 {w['slow'].format(n=SLOW_BELOW)}", INNER - 2, indent="   "))

    collection = []
    for species in SPECIES:
        if species in state.unlocked:
            collection.append(f"{ICONS[species]} {stage_for_xp(state.plants.get(species, 0))}/{STAGES}")
        else:
            collection.append("🔒")
    lines.append(row(f"{w['garden']:<{label}}" + "  ".join(collection)))
    if state.badges:
        labels = BADGE_LABELS.get(lang, BADGE_LABELS["en"])
        for i, text in enumerate(wrap_items([labels.get(b, b) for b in state.badges], INNER - 2 - label)):
            lines.append(row(f"{w['badges'] if i == 0 else '':<{label}}{text}"))

    lines.append(f"├{rule}┤")
    for note in notes or []:
        lines.extend(row(text) for text in wrap(note, INNER - 2, indent="   "))
    lines.extend(row(text) for text in wrap("💡 " + pick_tip(state, lang, seed), INNER - 2, indent="   "))
    lines.append(f"└{rule}┘")
    return lines


def notes_for(state: GardenState, events: List[Event], wanted_species: Optional[str], lang: str) -> List[str]:
    """What to tell the gardener this turn: the turn's events, and a locked species they asked for."""
    notes = [event_line(e, lang) for e in events]
    if wanted_species and wanted_species not in state.unlocked and not unlock_rule_met(wanted_species, state):
        notes.append(locked_line(wanted_species, lang))
    return notes
