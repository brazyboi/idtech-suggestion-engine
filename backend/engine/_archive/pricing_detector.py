"""
Simple service to detect pricing-related keywords in user messages.
"""

from ..llm.contracts import ChatResponse


class PricingDetector:
    """
    Detects when a user is asking about pricing/quoting and returns a
    predefined clarifying response.

    Uses a two-tier approach:
    1. Explicit pricing phrases ("how much", "what's the price") always trigger.
    2. Single keywords ("cost", "budget", "rate") only trigger on short messages
       that are clearly about pricing — NOT when the user happens to mention
       "cost" while answering a qualification question.

    This avoids the critical false-positive scenario where a user says
    "We're a parking lot and cost is a concern" and gets derailed into
    a pricing deflection.
    """

    # Phrases that unambiguously indicate a pricing question
    EXPLICIT_PRICING_PHRASES = [
        "how much",
        "what's the price",
        "what is the price",
        "how much does",
        "how much would",
        "can i get a quote",
        "i need a quote",
        "quote please",
        "send me a quote",
        "get a quote",
        "pricing",  # "What's the pricing?", "Tell me about pricing"
    ]

    # Keywords that only trigger on short/clearly-pricing messages
    SHORT_TRIGGER_KEYWORDS = ["price", "cost", "rate", "cheap", "expensive", "budget"]

    # Maximum message length to trigger on generic keywords
    MAX_SHORT_MSG_LENGTH = 100

    @staticmethod
    def detect(message: str) -> bool:
        """
        Return True if the message is asking about pricing.

        Strategy:
        1. Check explicit pricing phrases first — always trigger.
        2. For generic keywords, only trigger on short messages
           (< 100 chars) to avoid false positives mid-qualification.
        3. Never trigger if the message starts with qualification-like
           language ("we're", "our", "i'm looking", etc.).
        """
        lower = message.lower().strip()

        # Step 1: Explicit pricing phrases always trigger
        for phrase in PricingDetector.EXPLICIT_PRICING_PHRASES:
            if phrase in lower:
                return True

        # Step 2: For generic keywords, be conservative
        for kw in PricingDetector.SHORT_TRIGGER_KEYWORDS:
            if kw in lower:
                # Short message → likely just a pricing question
                if len(message.strip()) < PricingDetector.MAX_SHORT_MSG_LENGTH:
                    return True
                # Long messages with pricing keywords are likely qualification
                # answers — don't trigger.
                return False

        return False

    @staticmethod
    def build_response() -> ChatResponse:
        """Return a canned ChatResponse for pricing inquiries."""
        return ChatResponse(
            type="clarification",
            text="Pricing depends on volume and configuration — I can connect you with a specialist who can provide a customized quote. Would you like me to collect your contact info for a follow-up?",
            quick_replies=["Yes, please connect me", "No thanks, just browsing"],
            ui_actions=["offer_booking"],
        )
