"""
Tests for backend.agent.classifier.

Uses unittest.mock to avoid real OpenAI API calls.

Important: the classifier uses a module-level singleton (_classifier) that is
created at import time. We patch the singleton's client.chat.completions.create
method directly rather than patching the OpenAI constructor.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from backend.agent.classifier import _classifier, IntentClassifier


def _setup_mock_client(mock_create: MagicMock, intent_text: str) -> None:
    """Configure the mock create() to return a specific intent."""
    mock_choice = MagicMock()
    mock_choice.message.content = intent_text
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_create.return_value = mock_response


class TestClassifier:
    """classify_intent should return correct intent strings via mocked OpenAI."""

    def test_classify_greeting(self):
        """'hello' should be classified as greeting."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "greeting")
            intent, confidence, entities = _classifier.classify("hello")
        assert intent == "greeting"
        assert confidence == 1.0
        assert entities == {}

    def test_classify_product_search(self):
        """'i need a card reader' should be classified as product_search."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "product_search")
            intent, _, _ = _classifier.classify("i need a card reader for my store")
        assert intent == "product_search"

    def test_classify_qualification(self):
        """Answering about business should be classified as qualification."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "qualification")
            intent, _, _ = _classifier.classify("we're a parking lot")
        assert intent == "qualification"

    def test_classify_faq(self):
        """Asking about pricing should be classified as faq."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "faq")
            intent, _, _ = _classifier.classify("how much does it cost")
        assert intent == "faq"

    def test_classify_lead_capture(self):
        """Sharing contact info should be classified as lead_capture."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "lead_capture")
            intent, _, _ = _classifier.classify("yes, connect me")
        assert intent == "lead_capture"

    def test_classify_escalate(self):
        """Asking to speak to someone should be classified as escalate."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "escalate")
            intent, _, _ = _classifier.classify("talk to a person")
        assert intent == "escalate"

    def test_classify_chitchat(self):
        """Off-topic messages should be classified as chitchat."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "chitchat")
            intent, _, _ = _classifier.classify("what's the weather")
        assert intent == "chitchat"

    def test_unknown_intent_defaults_to_qualification(self):
        """Unknown intent strings should fall back to qualification."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "some_random_intent")
            intent, confidence, _ = _classifier.classify("hello")
        assert intent == "qualification"
        assert confidence == 1.0

    def test_api_error_fallback(self):
        """API errors should fall back to qualification with 0 confidence."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            mock_create.side_effect = Exception("API error")
            intent, confidence, entities = _classifier.classify("hello")
        assert intent == "qualification"
        assert confidence == 0.0
        assert "error" in entities

    def test_empty_response_fallback(self):
        """Empty response should fall back to qualification."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "")
            intent, _, _ = _classifier.classify("hello")
        assert intent == "qualification"

    def test_case_insensitive_response(self):
        """Uppercase response should be normalized."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "GREETING")
            intent, _, _ = _classifier.classify("hello")
        assert intent == "greeting"

    def test_whitespace_trimmed(self):
        """Whitespace around response should be trimmed."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "  greeting  ")
            intent, _, _ = _classifier.classify("hello")
        assert intent == "greeting"

    def test_short_answer_all_of_them_is_qualification(self):
        """'all of them' should be classified as qualification (short answer continuation).

        This is a critical edge case — the classifier was previously classifying
        short continuation answers like "all of them", "what?", "huh?" as chitchat,
        which caused the bot to loop with the same generic response.
        """
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "qualification")
            intent, _, _ = _classifier.classify("all of them")
        assert intent == "qualification"

    def test_short_answer_yes_is_qualification(self):
        """Short affirmative answers should be classified as qualification."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "qualification")
            intent, _, _ = _classifier.classify("yes")
        assert intent == "qualification"

    def test_short_answer_no_is_qualification(self):
        """Short negative answers should be classified as qualification."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "qualification")
            intent, _, _ = _classifier.classify("no")
        assert intent == "qualification"

    def test_i_just_told_you_is_qualification(self):
        """'I just told you' is a frustrated continuation, not chitchat."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "qualification")
            intent, _, _ = _classifier.classify("i just told you")
        assert intent == "qualification"

    def test_what_is_qualification_in_context(self):
        """'what?' or 'huh?' are confused continuations, not chitchat."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "qualification")
            intent, _, _ = _classifier.classify("what?")
        assert intent == "qualification"

    def test_outdoor_is_qualification(self):
        """'outdoor' is clearly a qualification answer."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "qualification")
            intent, _, _ = _classifier.classify("outdoor")
        assert intent == "qualification"

    def test_truly_off_topic_still_chitchat(self):
        """Clear off-topic jokes should still be chitchat."""
        with patch.object(_classifier.client.chat.completions, "create") as mock_create:
            _setup_mock_client(mock_create, "chitchat")
            intent, _, _ = _classifier.classify("tell me a joke")
        assert intent == "chitchat"
