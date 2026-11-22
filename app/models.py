"""Explicit local model preference; no automatic downloads or inference fallback."""
DEFAULT_MODEL = 'gemma4:e2b'
SMALL_MODEL = 'gemma3:1b'
MODEL_LABELS = {
    DEFAULT_MODEL: 'Lightweight · Gemma 4 E2B',
    SMALL_MODEL: 'Gemma 3 1B',
}


def preferred_model(installed):
    for name in (DEFAULT_MODEL, SMALL_MODEL, 'llama3.2:3b'):
        if name in installed:
            return name
    return installed[0] if installed else None
