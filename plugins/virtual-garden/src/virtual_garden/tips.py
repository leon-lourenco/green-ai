"""Gardener tips: one per turn, about whatever the garden needs most."""

from __future__ import annotations

import random
from typing import Dict, List

from .models import GardenState

TIPS: Dict[str, Dict[str, List[str]]] = {
    "soil": {
        "en": [
            "Long context? Prune it with /compact: every call re-reads the whole conversation.",
            "A new task deserves a new session: fresh soil, and nothing old to re-read.",
            "Paste the lines that matter, not whole logs: big dumps stay in the context for good.",
        ],
        "pt": [
            "Contexto longo? Pode com /compact: cada chamada relê a conversa inteira.",
            "Tarefa nova pede sessão nova: solo fresco e nada antigo para reler.",
            "Cole as linhas que importam, não o log inteiro: o que entra no contexto fica nele.",
        ],
    },
    "sun": {
        "en": [
            "Cached prompts cost a fraction of the compute: keep sessions going instead of restarting.",
            "Long pauses let the prompt cache expire; resuming soon keeps the sun out.",
            "Switching models mid-session starts the cache over; stick with one while you work.",
        ],
        "pt": [
            "Prompt em cache custa uma fração do processamento: continue a sessão em vez de recomeçar.",
            "Pausas longas deixam o cache expirar; voltar logo mantém o sol aberto.",
            "Trocar de modelo no meio da sessão zera o cache; fique em um enquanto trabalha.",
        ],
    },
    "any": {
        "en": [
            "For simple edits, a small model uses a fraction of the energy of a large one.",
            "A clear prompt with its constraints up front saves a round trip.",
            "Ask for the change, not the whole file back: fewer output tokens, less energy.",
            "Every plant you grow to Majestic stays in your collection.",
        ],
        "pt": [
            "Para edições simples, um modelo pequeno gasta uma fração da energia de um grande.",
            "Um prompt claro, com as restrições logo no início, economiza uma ida e volta.",
            "Peça a mudança, não o arquivo inteiro de volta: menos tokens de saída, menos energia.",
            "Toda planta que chega a Majestosa fica na sua coleção.",
        ],
    },
}

NEEDS_CARE_BELOW = 70


def pick_tip(state: GardenState, lang: str, seed: str = "") -> str:
    """A tip about the weakest of soil and sun, or a general one when both are fine."""
    lang = lang if lang in TIPS["any"] else "en"
    if min(state.soil, state.vitality) < NEEDS_CARE_BELOW:
        topic = "soil" if state.soil <= state.vitality else "sun"
    else:
        topic = "any"
    return random.Random(seed or None).choice(TIPS[topic][lang])
