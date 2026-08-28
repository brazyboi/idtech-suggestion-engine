"""
get_solution_content tool — reads pre-written solution narratives.

Returns vertical-specific content to help the agent explain why certain
products fit the customer's use case.
"""

import json
import os
from typing import Any, Dict

# Load once at module level
_knowledge_dir = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge")
_solution_path = os.path.join(_knowledge_dir, "solution_content.json")

_solution_cache: Dict[str, Any] | None = None


def _load_solution_content() -> Dict[str, Any]:
    global _solution_cache
    if _solution_cache is None:
        try:
            with open(_solution_path, "r") as f:
                _solution_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _solution_cache = {"verticals": {}}
    return _solution_cache


def get_solution_content(vertical: str) -> Dict[str, Any]:
    """
    Get pre-written solution content for a specific vertical.

    Returns a dict with:
        - narrative: the solution narrative
        - key_differentiators: key selling points
    Or an error if the vertical isn't found.
    """
    data = _load_solution_content()
    verticals = data.get("verticals", {})

    # Try exact match first, then case-insensitive
    if vertical in verticals:
        content = verticals[vertical]
    else:
        # Case-insensitive lookup
        match = None
        lower = vertical.lower()
        for key, value in verticals.items():
            if key.lower() == lower:
                match = value
                break
        if not match:
            return {
                "error": f"No solution content found for '{vertical}'.",
                "available_verticals": list(verticals.keys()),
            }
        content = match

    return {
        "vertical": vertical,
        "narrative": content.get("narrative", ""),
        "key_differentiators": content.get("key_differentiators", []),
    }
