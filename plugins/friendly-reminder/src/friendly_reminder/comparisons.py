"""Everyday things to compare an amount of water with.

``progressive``: a ladder from a glass to a minute of Iguaçu Falls; each
amount is compared with the largest step it fills, so the comparison grows
with the day's and the month's use.

``random``: a playful thing picked for each response. The pick is seeded by
the turn, so redrawing the same response shows the same thing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

MODES = ("progressive", "random")


@dataclass(frozen=True)
class Unit:
    ml: float
    # language -> (one, many, "a/um ..." for a share of a single one)
    names: Dict[str, Tuple[str, str, str]]


# Ordered smallest to largest; each step is roughly 10x the last.
LADDER: List[Unit] = [
    Unit(190, {"en": ("small glass", "small glasses", "a small glass"),
               "pt": ("copo americano", "copos americanos", "um copo americano")}),
    Unit(2_000, {"en": ("2-liter bottle", "2-liter bottles", "a 2-liter bottle"),
                 "pt": ("garrafa de 2 L", "garrafas de 2 L", "uma garrafa de 2 L")}),
    Unit(10_000, {"en": ("bucket", "buckets", "a bucket"),
                  "pt": ("balde", "baldes", "um balde")}),
    Unit(150_000, {"en": ("full bathtub", "full bathtubs", "a full bathtub"),
                   "pt": ("banheira cheia", "banheiras cheias", "uma banheira cheia")}),
    Unit(1_000_000, {"en": ("1,000 L water tank", "1,000 L water tanks", "a 1,000 L water tank"),
                     "pt": ("caixa d'água de 1.000 L", "caixas d'água de 1.000 L", "uma caixa d'água de 1.000 L")}),
    Unit(10_000_000, {"en": ("water truck", "water trucks", "a water truck"),
                      "pt": ("caminhão-pipa", "caminhões-pipa", "um caminhão-pipa")}),
    Unit(2_500_000_000, {"en": ("Olympic pool", "Olympic pools", "an Olympic pool"),
                         "pt": ("piscina olímpica", "piscinas olímpicas", "uma piscina olímpica")}),
    # Iguaçu's average flow is about 1,500 m³/s: 90 million liters a minute.
    Unit(90_000_000_000, {"en": ("minute of Iguaçu Falls", "minutes of Iguaçu Falls", "a minute of Iguaçu Falls"),
                          "pt": ("minuto das Cataratas do Iguaçu", "minutos das Cataratas do Iguaçu",
                                 "um minuto das Cataratas do Iguaçu")}),
]

FUN: List[Unit] = [
    Unit(0.05, {"en": ("raindrop", "raindrops", "a raindrop"),
                "pt": ("gota de chuva", "gotas de chuva", "uma gota de chuva")}),
    Unit(5, {"en": ("teaspoon", "teaspoons", "a teaspoon"),
             "pt": ("colher de chá", "colheres de chá", "uma colher de chá")}),
    Unit(30, {"en": ("ice cube", "ice cubes", "an ice cube"),
              "pt": ("cubo de gelo", "cubos de gelo", "um cubo de gelo")}),
    Unit(30, {"en": ("espresso shot", "espresso shots", "an espresso shot"),
              "pt": ("dose de espresso", "doses de espresso", "uma dose de espresso")}),
    # A thirsty camel can drink about 100 L in 10 minutes.
    Unit(170, {"en": ("second of a thirsty camel drinking", "seconds of a thirsty camel drinking", ""),
               "pt": ("segundo de um camelo com sede bebendo", "segundos de um camelo com sede bebendo", "")}),
    Unit(250, {"en": ("cactus watering", "cactus waterings", "a cactus watering"),
               "pt": ("rega de cacto", "regas de cacto", "uma rega de cacto")}),
    Unit(300, {"en": ("green coconut", "green coconuts", "a green coconut"),
               "pt": ("coco verde", "cocos verdes", "um coco verde")}),
    Unit(350, {"en": ("soda can", "soda cans", "a soda can"),
               "pt": ("latinha de refri", "latinhas de refri", "uma latinha de refri")}),
    Unit(4_000, {"en": ("goldfish bowl", "goldfish bowls", "a goldfish bowl"),
                 "pt": ("aquário de peixinho dourado", "aquários de peixinho dourado", "um aquário de peixinho dourado")}),
    # A 5 kg watermelon is about 92% water.
    Unit(4_600, {"en": ("watermelon", "watermelons", "a watermelon"),
                 "pt": ("melancia", "melancias", "uma melancia")}),
    Unit(6_000, {"en": ("toilet flush", "toilet flushes", "a toilet flush"),
                 "pt": ("descarga", "descargas", "uma descarga")}),
    # An adult elephant drinks around 150 L a day.
    Unit(150_000, {"en": ("day of an elephant's drinking water", "days of an elephant's drinking water", ""),
                   "pt": ("dia de água de um elefante", "dias de água de um elefante", "")}),
]

RANDOM_MIN_COUNT = 0.15  # "18% of a green coconut" still pictures well
RANDOM_MAX_COUNT = 5_000  # beyond this a count stops meaning anything

PHRASES = {
    "en": {"share": "{pct} of {one}", "tiny": "under 1% of {one}", "count": "≈ {n} {name}"},
    "pt": {"share": "{pct} de {one}", "tiny": "menos de 1% de {one}", "count": "≈ {n} {name}"},
}


def _count(unit: Unit, ml: float, lang: str, number: Callable[[float, int], str]) -> str:
    one, many, a_one = unit.names[lang]
    n = ml / unit.ml
    if n < 0.95 and a_one:
        return PHRASES[lang]["share"].format(pct=number(100 * n, 0) + "%", one=a_one)
    text = number(n, 1) if n < 10 and round(n, 1) != round(n) else number(round(n), 0)
    return PHRASES[lang]["count"].format(n=text, name=one if text == "1" else many)


def progressive(ml: float, lang: str, number: Callable[[float, int], str]) -> str:
    first = LADDER[0]
    if ml < first.ml:
        pct = 100 * ml / first.ml
        phrase = PHRASES[lang]["tiny" if pct < 1 else "share"]
        return phrase.format(pct=number(pct, 0) + "%", one=first.names[lang][2])
    unit = next(u for u in reversed(LADDER) if ml >= u.ml)
    return _count(unit, ml, lang, number)


def pick(ml: float, seed: str) -> Optional[Unit]:
    """One of the fun units the amount pictures well, chosen by ``seed``."""
    fits = [u for u in FUN if RANDOM_MIN_COUNT <= ml / u.ml <= RANDOM_MAX_COUNT]
    if not fits:
        return None
    index = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(fits)
    return fits[index]


def compare(ml: float, mode: str, lang: str, seed: str, number: Callable[[float, int], str]) -> str:
    lang = lang if lang in PHRASES else "en"
    if mode == "random":
        unit = pick(ml, seed)
        if unit is not None:
            return _count(unit, ml, lang, number)
    return progressive(ml, lang, number)
