"""Explicit local model preference; no automatic downloads or inference fallback."""
DEFAULT_MODEL = 'gemma4:e2b'
MODEL_LABELS = {DEFAULT_MODEL: 'Lightweight · Gemma 4 E2B'}


def preferred_model(installed):
    for name in (DEFAULT_MODEL, 'llama3.2:3b'):
        if name in installed:
            return name
    return installed[0] if installed else None
