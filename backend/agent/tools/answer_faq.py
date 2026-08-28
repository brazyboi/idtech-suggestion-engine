"""
answer_faq tool — reads approved FAQ answers.

Returns verbatim answers that the agent MUST present as-is for
legal/marketing accuracy. The agent should never paraphrase FAQ answers.
"""

import json
import os
from typing import Any, Dict

# Load once at module level
_knowledge_dir = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge")
_faq_path = os.path.join(_knowledge_dir, "faq.json")

_faq_cache: Dict[str, Any] | None = None


def _load_faq() -> Dict[str, Any]:
    global _faq_cache
    if _faq_cache is None:
        try:
            with open(_faq_path, "r") as f:
                _faq_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _faq_cache = {"topics": {}}
    return _faq_cache


def answer_faq(topic: str) -> Dict[str, Any]:
    """
    Get the approved answer for an FAQ topic.

    The agent MUST present the answer exactly as returned.
    Do not paraphrase or add information.

    Available topics: pricing, shipping, warranty, returns,
    compatibility, security, support, general.
    """
    data = _load_faq()
    topics = data.get("topics", {})

    # Case-insensitive lookup
    lower = topic.lower().strip()
    if lower in topics:
        entry = topics[lower]
    else:
        # Try partial match
        match = None
        for key, value in topics.items():
            if key in lower or lower in key:
                match = value
                break
        if not match:
            entry = topics.get("general", {"answer": "A sales rep can help with that. Would you like me to connect you?"})
        else:
            entry = match

    return {
        "topic": topic,
        "answer": entry.get("answer", ""),
        "_instruction": "Present this answer VERBATIM to the customer. Do not paraphrase.",
    }
