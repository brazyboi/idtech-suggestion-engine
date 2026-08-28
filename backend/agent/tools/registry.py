"""
OpenAI-format tool schema definitions for the agentic loop.

Each tool has a name, description, and JSON Schema parameters.
The agent (gpt-4o) sees these and decides which tool to call.

All product data comes from tools — the agent must NEVER name products
from its training knowledge.
"""

from typing import List, Dict, Any

# ── Tool Schemas ────────────────────────────────────────────────────────

SEARCH_PRODUCTS_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_products",
        "description": (
            "Search the ID TECH product catalog for payment hardware matching "
            "the customer's requirements. Use this when the customer describes "
            "their use case, environment, or technical needs. Returns a list of "
            "matching products with key specifications. Never guess product names "
            "— always use this tool to find them."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "use_case": {
                    "type": "string",
                    "description": "The customer's industry/vertical: parking, transit, retail, vending, EV charging, hospitality, healthcare."
                },
                "category": {
                    "type": "string",
                    "description": "Product category if known: card reader, PIN pad, all-in-one terminal, display."
                },
                "input_power": {
                    "type": "string",
                    "description": "Power requirement: USB, VAC (wall outlet), battery, PoE."
                },
                "interface": {
                    "type": "string",
                    "description": "Host interface needed: USB, RS232/Serial, Ethernet, Bluetooth."
                },
                "is_outdoor": {
                    "type": "boolean",
                    "description": "Whether the device will be deployed outdoors."
                },
                "is_standalone": {
                    "type": "boolean",
                    "description": "Whether the device needs to operate standalone (no host computer)."
                },
                "extra_tags": {
                    "type": "string",
                    "description": "Comma-separated extra requirements: PIN, display, contactless, keypad."
                },
                "query": {
                    "type": "string",
                    "description": "Free-text search for model name or other keywords."
                },
            },
            "required": [],
        },
    },
}

GET_PRODUCT_DETAILS_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_product_details",
        "description": (
            "Get detailed specifications, compatible software, installation "
            "documentation, and highlights for a specific product by model name. "
            "Use this after search_products to drill into a product the customer "
            "is interested in."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "model_name": {
                    "type": "string",
                    "description": "The exact model name of the hardware product."
                },
            },
            "required": ["model_name"],
        },
    },
}

GET_SOLUTION_CONTENT_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_solution_content",
        "description": (
            "Get pre-written solution narrative and key differentiators for a "
            "specific industry/vertical. Use this to provide rich context when "
            "explaining why certain products fit the customer's use case."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "vertical": {
                    "type": "string",
                    "description": "The canonical use case name: Parking Payment Systems, Transit Payment Solutions, Loyalty Program Contactless Readers, Vending Payment Systems, EV Charging Station Payment Solutions."
                },
            },
            "required": ["vertical"],
        },
    },
}

ANSWER_FAQ_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "answer_faq",
        "description": (
            "Get the approved answer for a frequently asked question. Use this "
            "when the customer asks about pricing, shipping, warranty, returns, "
            "compatibility, security, or support. You MUST present the answer "
            "exactly as returned — do not paraphrase or add information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The FAQ topic: pricing, shipping, warranty, returns, compatibility, security, support, general."
                },
            },
            "required": ["topic"],
        },
    },
}

SUBMIT_LEAD_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_lead",
        "description": (
            "Submit the customer's contact information to the sales team for "
            "follow-up. Use this when the customer has agreed to be contacted "
            "or when wrapping up a qualified conversation. Only call this once "
            "per conversation — after calling it, guide the conversation toward "
            "a natural close. Requires at minimum a name and email."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The customer's full name."
                },
                "email": {
                    "type": "string",
                    "description": "The customer's email address."
                },
                "company": {
                    "type": "string",
                    "description": "The customer's company or organization (optional)."
                },
                "phone": {
                    "type": "string",
                    "description": "The customer's phone number (optional)."
                },
            },
            "required": ["name", "email"],
        },
    },
}

ESCALATE_TO_SALES_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "escalate_to_sales",
        "description": (
            "Immediately escalate the conversation to a sales rep. "
            "Use this when the customer explicitly asks to speak to someone, "
            "has a complex or sensitive question you cannot answer, or is "
            "frustrated. Submits their contact info and flags the lead as urgent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The customer's name (if known, otherwise ask)."
                },
                "email": {
                    "type": "string",
                    "description": "The customer's email (if known, otherwise ask)."
                },
                "reason": {
                    "type": "string",
                    "description": "Brief reason for escalation."
                },
            },
            "required": ["reason"],
        },
    },
}

CAPTURE_LEAD_INFO_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "capture_lead_info",
        "description": (
            "Silently capture lead contact information when the customer "
            "volunteers it during conversation. Use this passively — do NOT "
            "ask for information just to fill this out. Only capture what "
            "the customer has already shared. The system uses this to build "
            "a profile for follow-up."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Customer's name if they mentioned it."
                },
                "email": {
                    "type": "string",
                    "description": "Customer's email if they shared it."
                },
                "company": {
                    "type": "string",
                    "description": "Customer's company if they mentioned it."
                },
                "phone": {
                    "type": "string",
                    "description": "Customer's phone if they shared it."
                },
            },
            "required": [],
        },
    },
}


# ── Tool Sets ───────────────────────────────────────────────────────────

def get_all_tools() -> List[Dict[str, Any]]:
    """Return all available tools for the agent."""
    return [
        SEARCH_PRODUCTS_TOOL,
        GET_PRODUCT_DETAILS_TOOL,
        GET_SOLUTION_CONTENT_TOOL,
        ANSWER_FAQ_TOOL,
        SUBMIT_LEAD_TOOL,
        ESCALATE_TO_SALES_TOOL,
        CAPTURE_LEAD_INFO_TOOL,
    ]


def get_tools_for_intent(intent: str) -> List[Dict[str, Any]]:
    """
    Return a filtered set of tools based on the classified intent.
    This reduces the tool surface the LLM sees, making decisions faster
    and reducing hallucination risk.
    """
    base = [CAPTURE_LEAD_INFO_TOOL]  # Always available for passive capture

    intent_tools: Dict[str, List[Dict[str, Any]]] = {
        "product_search": [
            SEARCH_PRODUCTS_TOOL,
            GET_PRODUCT_DETAILS_TOOL,
            GET_SOLUTION_CONTENT_TOOL,
        ],
        "faq": [ANSWER_FAQ_TOOL],
        "qualification": [
            SEARCH_PRODUCTS_TOOL,
            GET_SOLUTION_CONTENT_TOOL,
        ],
        "lead_capture": [SUBMIT_LEAD_TOOL],
        "escalate": [ESCALATE_TO_SALES_TOOL, SUBMIT_LEAD_TOOL],
        "greeting": [
            SEARCH_PRODUCTS_TOOL,
            ANSWER_FAQ_TOOL,
        ],
        "chitchat": [ANSWER_FAQ_TOOL],
    }

    return base + intent_tools.get(intent, get_all_tools())
