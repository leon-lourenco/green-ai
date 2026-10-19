# Contributing to Friendly Reminder

Thanks for your interest! Friendly Reminder has zero runtime dependencies — any contribution must keep it that way.

## Running the tests

```bash
# From the plugin root:
python3 -m unittest discover -s tests
```

All tests run in a few seconds with nothing but the standard library.

## Adding or updating prices

Edit [`data/pricing.json`](data/pricing.json). The schema is:

```jsonc
{
  "as_of": "YYYY-MM-DD",
  "source": "URL",
  "models": {
    "model-id": {
      "input": <USD/M tokens>,
      "output": <USD/M tokens>,
      "cache_read": <USD/M tokens>,          // optional
      "long_context": {                       // optional
        "above_prompt_tokens": 100000,
        "input": ...,
        "output": ...,
        "cache_read": ...
      },
      "fast": { "input": ..., "output": ... } // optional, for fast-mode variants
    }
  }
}
```

`model-id` must match the output of `normalize_model()` in [`pricing.py`](src/friendly_reminder/pricing.py). Run `normalize_model("Your Model Name (Qualifier)")` in a Python shell to confirm the right key.

## Adding a new platform adapter

1. Create `src/friendly_reminder/adapters/<platform>.py` that turns the tool's transcript into `ApiCall`s, then reuses `meter.aggregate`, `history.record` and `render.render`.
2. Record each turn under a key that the tool's hook and a manual run both derive the same way, so a turn is never counted twice.
3. Add a launcher in `scripts/` and tests in `tests/test_<platform>_adapter.py`.

The agy adapter ([`adapters/agy.py`](src/friendly_reminder/adapters/agy.py)) is the reference implementation.

## Updating the environmental footprint factors

Edit [`data/footprint.json`](data/footprint.json). Please add or update the `sources` array whenever you change a factor, and bump the `as_of` date.

## Code style

The project uses [ruff](https://docs.astral.sh/ruff/) with the settings in `pyproject.toml`. Run:

```bash
ruff check src tests
```

Target is Python 3.8+ — avoid syntax or stdlib features added after 3.8.

## What we won't add

- Runtime dependencies (no `requests`, `httpx`, `pydantic`, …)
- Windows-only or macOS-only paths without a cross-platform fallback
- Network calls from the hook (the hook runs in-process on every response)
