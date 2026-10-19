"""The botanical catalog: each species' names, unlock rule and ASCII sprites.

Every sprite is a block of lines drawn as one piece: the renderer pads the
block to its widest line and centers the block, never single lines, so the
drawing keeps its shape. All sprites stand in the same pot.
"""

from __future__ import annotations

from typing import Dict, List

# The order species are listed in the collection.
SPECIES: List[str] = ["bonsai", "cactus", "sakura", "ipe"]
STARTER = "bonsai"
STAGES = 6

ICONS: Dict[str, str] = {"bonsai": "🎍", "cactus": "🌵", "sakura": "🌸", "ipe": "🌼"}

NAMES: Dict[str, Dict[str, str]] = {
    "en": {"bonsai": "Bonsai", "cactus": "Cactus", "sakura": "Sakura", "ipe": "Golden Ipê"},
    "pt": {"bonsai": "Bonsai", "cactus": "Mandacaru", "sakura": "Cerejeira", "ipe": "Ipê-amarelo"},
}

STAGE_NAMES: Dict[str, List[str]] = {
    "en": ["Seed", "Sprout", "Sapling", "Young plant", "Blooming", "Majestic"],
    "pt": ["Semente", "Broto", "Muda", "Planta jovem", "Florescendo", "Majestosa"],
}

POT = [
    "   \\=======/   ",
    "    \\_____/    ",
]

_SEED = [
    "               ",
    "       .       ",
]

_SPROUT = [
    "       ,       ",
    "      \\|/      ",
]

ART: Dict[str, List[List[str]]] = {
    "bonsai": [
        _SEED,
        _SPROUT,
        [
            "     .-~-.     ",
            "    (  ~  )    ",
            "     '-|-'     ",
            "       |       ",
        ],
        [
            "    .-~~~-.    ",
            "   ( ~ ~ ~ )   ",
            "    '-.|.-'.-. ",
            "       |__(~ ) ",
            "       |   '-' ",
            "       |       ",
        ],
        [
            " .-~~-.  .-~-. ",
            "( ~  ~ )( ~ ~ )",
            " '-.\\.-' '-/-' ",
            "     \\ \\__/    ",
            "      \\ |      ",
            "       |       ",
        ],
        [
            "    .-~~~~~~-.     ",
            " .-(  ~  ~  ~ )-.  ",
            "( ~ '-.\\ | /.-' ~ ) ",
            " '-~-. \\\\|// .-~-'  ",
            "      '._|_.'      ",
            "         |         ",
        ],
    ],
    "cactus": [
        _SEED,
        [
            "       _       ",
            "      ( )      ",
        ],
        [
            "       _       ",
            "      | |      ",
            "      | |      ",
        ],
        [
            "       _       ",
            "    _ | |      ",
            "   | || |  _   ",
            "    \\_  | | |  ",
            "      | |_/ /  ",
            "      | |      ",
        ],
        [
            "       *       ",
            "    * | | *    ",
            "   | || || |   ",
            "    \\_  |_/    ",
            "      | |      ",
            "      | |      ",
        ],
        [
            "    *   *   *    ",
            "   | | | | | |   ",
            "   | | | | | |   ",
            "    \\ \\| |/ /    ",
            "     \\_   _/     ",
            "       | |       ",
            "       | |       ",
        ],
    ],
    "sakura": [
        _SEED,
        _SPROUT,
        [
            "     . * .     ",
            "      \\|/      ",
            "       |       ",
        ],
        [
            "    * . * .    ",
            "   . \\ | / *   ",
            "     \\\\|//     ",
            "       |       ",
        ],
        [
            "  * o * o * o  ",
            " o * \\ | / * o ",
            "  * o \\|/ o *  ",
            "       |       ",
            "       |       ",
        ],
        [
            "  o * o * o * o  ",
            " * o * \\ | / o * ",
            "o * o * \\|/ * o *",
            " * o *  \\|/  o * ",
            "         |    *  ",
            "    *    |       ",
        ],
    ],
    "ipe": [
        _SEED,
        _SPROUT,
        [
            "      \\ /      ",
            "       Y       ",
            "       |       ",
        ],
        [
            "    \\  |  /    ",
            "     \\ | /     ",
            "      \\|/      ",
            "       |       ",
        ],
        [
            "   @ \\ @ / @   ",
            "  @ @ \\|/ @ @  ",
            "   @   |   @   ",
            "       |       ",
            "       |       ",
        ],
        [
            "  @ @ @ @ @ @ @  ",
            " @ @ \\ @ | @ / @ ",
            "@ @ @ \\ @|@ / @ @",
            "  @ @  \\ | /  @  ",
            "        \\|/   @  ",
            "  @      |       ",
            "         |       ",
        ],
    ],
}


def clamp_stage(stage: int) -> int:
    return max(1, min(STAGES, stage))


def _trunk_column(line: str) -> int:
    """Where the plant meets the soil: a lone ``|``, or the middle of what is drawn."""
    if line.count("|") == 1:
        return line.index("|")
    drawn = line.strip()
    start = line.index(drawn[0]) if drawn else 0
    return start + (len(drawn) - 1) // 2


def sprite(species: str, stage: int) -> List[str]:
    """The plant standing in its pot, top to bottom, the pot under the trunk."""
    plant = ART.get(species, ART[STARTER])[clamp_stage(stage) - 1]
    shift = _trunk_column(plant[-1]) - _trunk_column(POT[0])
    if shift >= 0:
        return plant + [" " * shift + line for line in POT]
    return [" " * -shift + line for line in plant] + POT


def species_name(species: str, lang: str) -> str:
    return NAMES.get(lang, NAMES["en"]).get(species, species)


def stage_name(stage: int, lang: str) -> str:
    return STAGE_NAMES.get(lang, STAGE_NAMES["en"])[clamp_stage(stage) - 1]
