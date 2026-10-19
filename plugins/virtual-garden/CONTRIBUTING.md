# Contributing to Virtual Garden

Virtual Garden has zero runtime dependencies, and any contribution must keep it that way.

Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): it maps the components, module dependencies, the flow of a turn and the data model.

## Running the tests

```bash
# From the plugin root:
python3 -m unittest discover -s tests
```

## Adding a species

1. Add it to `SPECIES`, `ICONS` and `NAMES` in [`species.py`](src/virtual_garden/species.py), with six sprites in `ART`. Sprites stand in the shared `POT`: end each one with its trunk (a lone `|`) or its center over the pot.
2. Give it an unlock rule in `unlock_rule_met` ([`engine.py`](src/virtual_garden/engine.py)) and a hint in `UNLOCK_HINTS` ([`render.py`](src/virtual_garden/render.py)).
3. Add it to the `species` options in `.claude-plugin/plugin.json` and `CHOICES` in `hooks/register.tsx`.

`tests/test_render.py` checks that every sprite fits the box and that every line of the box has the same width in both languages.

## Adding a platform adapter

Create `src/virtual_garden/adapters/<platform>.py` that turns the tool's transcript into a turn key and `TurnMetrics`, then calls `state.record_turn`. Derive the key the same way in the hook and in a manual run, so a turn is never counted twice. [`adapters/agy.py`](src/virtual_garden/adapters/agy.py) is the reference.

## Code style

The project uses [ruff](https://docs.astral.sh/ruff/) with the settings in `pyproject.toml`:

```bash
ruff check src tests
```

Target is Python 3.8+: avoid syntax or stdlib features added after 3.8.

## What we won't add

- Runtime dependencies
- Penalties that shame: a careless turn may slow the plant down, never kill it
- Network calls from the hook
