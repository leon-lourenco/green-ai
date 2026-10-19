"""What the Claude Code and agy entry points share: output, manual commands, error log."""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime
from typing import Dict, List, Optional

from . import __version__
from .config import Settings, data_dir, resolved_language
from .engine import switch
from .models import Event, GardenState
from .render import notes_for, render_full, render_summary
from .species import SPECIES, species_name
from .state import editing, load_state

SWITCHED = {"en": "Now tending: {species}.", "pt": "Agora cuidando de: {species}."}


def wanted_species(settings: Settings) -> Optional[str]:
    return None if settings.species == "current" else settings.species


def present(state: GardenState, events: List[Event], settings: Settings, seed: str = "") -> Dict[str, object]:
    """Both views of the garden; ``systemMessage`` is the one the format asks for."""
    lang = resolved_language(settings)
    notes = notes_for(state, events, wanted_species(settings), lang)
    summary = render_summary(state, lang, notes)
    full = render_full(state, lang, notes, seed)
    out: Dict[str, object] = {"summary": summary, "full": full, "language": lang}
    if settings.format != "off":
        out["systemMessage"] = "\n".join(full if settings.format == "full" else summary)
    return out


def add_manual_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--text", action="store_true", help="Print the one-line summary")
    parser.add_argument("--full", "--ascii", dest="full", action="store_true", help="Print the full garden")
    parser.add_argument("--switch", metavar="SPECIES", choices=SPECIES, help="Tend another unlocked species")


def is_manual(args: argparse.Namespace) -> bool:
    return bool(args.text or args.full or args.switch)


def run_switch(species: str, settings: Settings) -> int:
    lang = resolved_language(settings)
    with editing(data_dir()) as state:
        ok = switch(state, species)
    if ok:
        sys.stdout.write(SWITCHED.get(lang, SWITCHED["en"]).format(species=species_name(species, lang)) + "\n")
    else:
        sys.stdout.write(notes_for(state, [], species, lang)[-1] + "\n")
    return 0


def print_garden(state: Optional[GardenState], events: List[Event], settings: Settings, full: bool) -> None:
    state = state or load_state(data_dir())
    view = present(state, events, settings)
    sys.stdout.write("\n".join(view["full" if full else "summary"]) + "\n")  # type: ignore[arg-type]


def log_error(source: str) -> None:
    folder = data_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "error.log").open("a", encoding="utf-8") as handle:
            handle.write(f"--- {datetime.now().isoformat()} {source} v{__version__}\n{traceback.format_exc()}\n")
    except OSError:
        pass
