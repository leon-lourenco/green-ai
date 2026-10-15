"""Turn totals into the text shown after each response.

Water comes first on purpose: the plugin exists to make the water cost of
each response visible, so it leads the message, gets a plain-language
comparison (a 250 mL glass), and heads the table.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Sequence

from .config import Billing, Settings
from .models import Quota, Totals

TITLE = "Friendly Reminder"
GLASS_ML = 250.0

STRINGS: Dict[str, Dict[str, str]] = {
    "en": {
        "turn_n": "turn {n}",
        "headline": "This response used ≈ {water} of water, {glass}.",
        "short_water": "≈ {water} of water in this response ({glass})",
        "short_quota": "{plan} quota: 5h {five}, week {week}",
        "glass_share": "{pct} of a glass",
        "glass_tiny": "under 1% of a glass",
        "glasses": "≈ {n} glasses",
        "glass_one": "≈ 1 glass",
        "history": "Today: ≈ {day} ({day_glasses}) · Month: ≈ {month} ({month_glasses})",
        "turn": "Turn",
        "today": "Today",
        "month": "Month",
        "water": "Water",
        "energy": "Energy",
        "tokens": "Tokens",
        "cost": "API cost",
        "quota": "{plan} quota: 5h {five} · week {week}",
        "quota_age": "updated {age} ago",
        "input": "Input",
        "cache_write": "Cache write",
        "cache_read": "Cache read",
        "output": "Output",
        "range": "{label}: {low} – {high}",
        "estimate": "≈ = estimate ({profile} profile; water counts {scope}). Glass = 250 mL.",
        "scope_full": "data-center cooling + power generation",
        "scope_onsite": "data-center cooling only",
        "unpriced": "no price for: {models}",
        "partner": "list price; {provider} pricing may differ",
        "partial": "final response not yet on disk; numbers may be low",
    },
    "pt": {
        "turn_n": "turno {n}",
        "headline": "Esta resposta consumiu ≈ {water} de água, {glass}.",
        "short_water": "≈ {water} de água nesta resposta ({glass})",
        "short_quota": "cota {plan}: 5h {five}, semana {week}",
        "glass_share": "{pct} de um copo",
        "glass_tiny": "menos de 1% de um copo",
        "glasses": "≈ {n} copos",
        "glass_one": "≈ 1 copo",
        "history": "Hoje: ≈ {day} ({day_glasses}) · Mês: ≈ {month} ({month_glasses})",
        "turn": "Turno",
        "today": "Hoje",
        "month": "Mês",
        "water": "Água",
        "energy": "Energia",
        "tokens": "Tokens",
        "cost": "Custo API",
        "quota": "Cota {plan}: 5h {five} · semana {week}",
        "quota_age": "atualizada há {age}",
        "input": "Entrada",
        "cache_write": "Cache (escrita)",
        "cache_read": "Cache (leitura)",
        "output": "Saída",
        "range": "{label}: {low} – {high}",
        "estimate": "≈ = estimativa (perfil {profile}; a água inclui {scope}). Copo = 250 mL.",
        "scope_full": "resfriamento do data center + geração de energia",
        "scope_onsite": "só o resfriamento do data center",
        "unpriced": "sem preço para: {models}",
        "partner": "preço de tabela; o preço na {provider} pode ser diferente",
        "partial": "resposta final ainda não gravada; os números podem estar baixos",
    },
}

CURRENCY_SYMBOLS = {"USD": ("$", "US$ "), "BRL": ("R$ ", "R$ "), "EUR": ("€", "€ "), "GBP": ("£", "£ ")}


class Formatter:
    def __init__(self, settings: Settings, language: str):
        self.s = settings
        self.lang = language if language in STRINGS else "en"
        self.t = STRINGS[self.lang]

    def number(self, value: float, decimals: int = 0) -> str:
        text = f"{value:,.{decimals}f}"
        if self.lang == "pt":
            text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
        return text

    def tokens(self, value: int, exact: bool = True) -> str:
        if exact or value < 10_000:
            return self.number(value)
        for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
            if value >= size:
                scaled = value / size
                return self.number(scaled, 1 if scaled < 100 else 0) + suffix
        return self.number(value)

    def money(self, usd: float, complete: bool = True) -> str:
        amount = usd * self.s.exchange_rate
        code = self.s.currency
        en_symbol, pt_symbol = CURRENCY_SYMBOLS.get(code, (code + " ", code + " "))
        symbol = pt_symbol if self.lang == "pt" else en_symbol
        decimals = 2 if amount == 0 or abs(amount) >= 1 else (3 if abs(amount) >= 0.1 else 4)
        return symbol + self.number(amount, decimals) + ("" if complete else "*")

    def _sig(self, value: float) -> str:
        if value == 0:
            return "0"
        if value >= 100:
            return self.number(value)
        if value >= 10:
            return self.number(value, 1)
        if value >= 1:
            return self.number(value, 2)
        return self.number(value, 3)

    def energy(self, wh: float) -> str:
        return self._sig(wh / 1000) + " kWh" if wh >= 1000 else self._sig(wh) + " Wh"

    def water(self, ml: float) -> str:
        return self._sig(ml / 1000) + " L" if ml >= 1000 else self._sig(ml) + " mL"

    def glasses(self, ml: float) -> str:
        """Water as a share of, or a count of, 250 mL glasses."""
        if ml < GLASS_ML:
            pct = 100 * ml / GLASS_ML
            return self.t["glass_tiny"] if pct < 1 else self.t["glass_share"].format(pct=self.number(pct) + "%")
        count = ml / GLASS_ML
        if round(count, 1) < 1.5:
            return self.t["glass_one"]
        return self.t["glasses"].format(n=self.number(count, 1 if count < 10 else 0))

    @staticmethod
    def age(fetched_at_ms: int) -> str:
        seconds = max(0, int(time.time() - fetched_at_ms / 1000))
        if seconds < 90:
            return f"{seconds}s"
        if seconds < 5400:
            return f"{seconds // 60} min"
        if seconds < 172800:
            return f"{seconds // 3600} h"
        return f"{seconds // 86400} d"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> List[str]:
    widths = [max(len(str(r[i])) for r in [headers, *rows]) for i in range(len(headers))]

    def line(left: str, mid: str, right: str) -> str:
        return left + mid.join("─" * (w + 2) for w in widths) + right

    def row(cells: Sequence[str]) -> str:
        parts = [f" {cells[0]:<{widths[0]}} "] + [f" {c:>{w}} " for c, w in zip(cells[1:], widths[1:])]
        return "│" + "│".join(parts) + "│"

    return [line("┌", "┬", "┐"), row(headers), line("├", "┼", "┤"), *[row(r) for r in rows], line("└", "┴", "┘")]


def _quota_line(f: Formatter, quota: Optional[Quota], billing: Billing) -> Optional[str]:
    if not (quota and billing.is_subscription):
        return None
    pct = lambda v: "-" if v is None else f.number(v) + "%"  # noqa: E731
    text = f.t["quota"].format(plan=quota.plan or "", five=pct(quota.five_hour_pct), week=pct(quota.seven_day_pct))
    if quota.fetched_at_ms:
        text += f" ({f.t['quota_age'].format(age=f.age(quota.fetched_at_ms))})"
    return text


def render(
    turn: Totals,
    turn_number: int,
    settings: Settings,
    language: str,
    billing: Billing,
    quota: Optional[Quota] = None,
    today: Optional[Totals] = None,
    month: Optional[Totals] = None,
    flushed: bool = True,
) -> Optional[str]:
    if settings.format == "off":
        return None
    f = Formatter(settings, language)
    t = f.t

    models = sorted(turn.models, key=lambda m: -turn.models[m])
    title = "💧 " + " · ".join(
        [TITLE, t["turn_n"].format(n=turn_number), ", ".join(m.replace("claude-", "") for m in models) or "-"]
    )
    water_ml = turn.footprint.water_ml
    headline = t["headline"].format(water=f.water(water_ml), glass=f.glasses(water_ml))
    history = (
        t["history"].format(
            day=f.water(today.footprint.water_ml),
            day_glasses=f.glasses(today.footprint.water_ml),
            month=f.water(month.footprint.water_ml),
            month_glasses=f.glasses(month.footprint.water_ml),
        )
        if today is not None and month is not None
        else None
    )
    quota_line = _quota_line(f, quota, billing)

    if settings.format == "short":
        first = ["💧 " + t["short_water"].format(water=f.water(water_ml), glass=f.glasses(water_ml))]
        if today is not None and month is not None:
            first += [
                f"{t['today'].lower()} ≈ {f.water(today.footprint.water_ml)}",
                f"{t['month'].lower()} ≈ {f.water(month.footprint.water_ml)}",
            ]
        second = [
            "⚡ ≈ " + f.energy(turn.footprint.wh),
            f"{f.tokens(turn.usage.total)} tokens",
            f.money(turn.cost_usd, turn.cost_complete),
        ]
        if quota and billing.is_subscription:
            pct = lambda v: "-" if v is None else f.number(v) + "%"  # noqa: E731
            second.append(t["short_quota"].format(
                plan=quota.plan or "", five=pct(quota.five_hour_pct), week=pct(quota.seven_day_pct)))
        lines = [" · ".join(first), " · ".join(second)]
        if not flushed:
            lines.append("! " + t["partial"])
        return "\n".join(lines)

    spans = [turn] + ([month] if month is not None else [])
    headers = ["", t["turn"]] + ([t["month"]] if month is not None else [])
    rows = [
        [t["water"]] + ["≈ " + f.water(s.footprint.water_ml) for s in spans],
        [t["energy"]] + ["≈ " + f.energy(s.footprint.wh) for s in spans],
        [t["tokens"]] + [f.tokens(s.usage.total, exact=(i == 0)) for i, s in enumerate(spans)],
        [t["cost"]] + [f.money(s.cost_usd, s.cost_complete) for s in spans],
    ]
    lines = [title, headline] + ([history] if history else []) + _table(headers, rows)

    if settings.format == "detailed":
        u = turn.usage
        lines += _table(
            ["", t["turn"]],
            [
                [t["input"], f.tokens(u.input)],
                [t["cache_write"] + " 5m", f.tokens(u.cache_write_5m)],
                [t["cache_write"] + " 1h", f.tokens(u.cache_write_1h)],
                [t["cache_read"], f.tokens(u.cache_read)],
                [t["output"], f.tokens(u.output)],
            ],
        )
        lo, hi = turn.footprint_low, turn.footprint_high
        lines.append(t["range"].format(label=t["water"], low=f.water(lo.water_ml), high=f.water(hi.water_ml)))
        lines.append(t["range"].format(label=t["energy"], low=f.energy(lo.wh), high=f.energy(hi.wh)))
        scope = t["scope_full"] if settings.water_scope == "full" else t["scope_onsite"]
        lines.append(t["estimate"].format(profile=settings.footprint_profile, scope=scope))

    if quota_line:
        lines.append(quota_line)
    if turn.unpriced_models:
        lines.append("* " + t["unpriced"].format(models=", ".join(sorted(turn.unpriced_models))))
    if billing.partner_pricing:
        lines.append(t["partner"].format(provider=billing.mode.capitalize()))
    if not flushed:
        lines.append("! " + t["partial"])
    return "\n".join(lines)
