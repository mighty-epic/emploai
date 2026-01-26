"""Model preference helpers for the TUI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

# Path for storing model preferences (recent, favorites)
MODEL_PREFS_FILE = Path(__file__).parent / ".model_prefs.json"


def _load_model_prefs() -> Dict:
    """Load model preferences from file."""
    if MODEL_PREFS_FILE.exists():
        try:
            with open(MODEL_PREFS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"recent": [], "favorites": []}


def _save_model_prefs(prefs: Dict) -> None:
    """Save model preferences to file."""
    try:
        with open(MODEL_PREFS_FILE, "w") as f:
            json.dump(prefs, f, indent=2)
    except IOError:
        pass


def _add_recent_model(model: str) -> None:
    """Add a model to recent list (max 3, most recent first)."""
    prefs = _load_model_prefs()
    recent = prefs.get("recent", [])
    # Remove if already exists
    if model in recent:
        recent.remove(model)
    # Add to front
    recent.insert(0, model)
    # Keep only 3
    prefs["recent"] = recent[:3]
    _save_model_prefs(prefs)


def _toggle_favorite(model: str) -> bool:
    """Toggle favorite status for a model. Returns new status."""
    prefs = _load_model_prefs()
    favorites = prefs.get("favorites", [])
    if model in favorites:
        favorites.remove(model)
        is_favorite = False
    else:
        favorites.append(model)
        is_favorite = True
    prefs["favorites"] = favorites
    _save_model_prefs(prefs)
    return is_favorite
