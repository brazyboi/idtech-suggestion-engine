"""
Tests for backend.agent.tools.get_product_details.

Focus: the exact-match / disambiguation behavior. This tool must never
silently return a *different* product than the one asked for — doing so
makes the agent confidently describe the wrong hardware to a customer
(the poka-yoke lesson from Anthropic's "Building Effective Agents",
Appendix 2). Runs against the in-memory SQLite DB via the
patch_direct_db_access fixture, since this tool calls SessionLocal()
directly rather than through FastAPI's get_db dependency.
"""

from backend.agent.tools.get_product_details import get_product_details
from backend.db.repositories.admin_repository import AdminRepository


def _seed(db_session):
    repo = AdminRepository(db_session)
    repo.create_hardware(
        model_name="VP3300",
        fields={"input_power": "USB", "interface": "USB"},
        categories=[],
        use_cases=[],
        software=[],
    )
    repo.create_hardware(
        model_name="VP3350",
        fields={"input_power": "USB", "interface": "USB"},
        categories=[],
        use_cases=[],
        software=[],
    )


class TestGetProductDetails:
    def test_exact_match_returns_that_product(self, db_session, patch_direct_db_access):
        _seed(db_session)
        result = get_product_details("VP3300")
        assert result.get("model_name") == "VP3300"
        assert "error" not in result

    def test_exact_match_is_case_insensitive(self, db_session, patch_direct_db_access):
        _seed(db_session)
        result = get_product_details("vp3300")
        assert result.get("model_name") == "VP3300"

    def test_no_rows_at_all_returns_not_found_error(self, db_session, patch_direct_db_access):
        _seed(db_session)
        result = get_product_details("ZZZ-nonexistent")
        assert "error" in result
        assert "did_you_mean" not in result  # nothing even close

    def test_partial_match_does_not_silently_return_wrong_product(
        self, db_session, patch_direct_db_access
    ):
        """'VP33' fuzzy-matches both VP3300 and VP3350 but exactly matches
        neither. The tool must NOT pick one silently — it must return an
        error with candidates so the agent can disambiguate."""
        _seed(db_session)
        result = get_product_details("VP33")
        assert "error" in result
        assert "model_name" not in result  # did NOT return a product
        assert set(result["did_you_mean"]) == {"VP3300", "VP3350"}

    def test_two_char_typo_suggests_instead_of_dead_ending(self, db_session, patch_direct_db_access):
        """'VP33OO' (letters instead of zeros) is too different from
        'VP3300' to auto-resolve (2 of 6 chars wrong — same 'don't guess'
        rule as test_partial_match_does_not_silently_return_wrong_product),
        but it must still surface it as a suggestion instead of the old
        behavior: ILIKE finds zero rows for a non-substring typo, so it used
        to dead-end with no candidates at all."""
        _seed(db_session)
        result = get_product_details("VP33OO")
        assert "error" in result
        assert "model_name" not in result
        assert "VP3300" in result["did_you_mean"]

    def test_extra_whitespace_still_resolves(self, db_session, patch_direct_db_access):
        """A stray space must not defeat matching — this used to fail the
        exact-equality check even though ILIKE found the row."""
        _seed(db_session)
        result = get_product_details("VP 3300")
        assert result.get("model_name") == "VP3300"
        assert "error" not in result

    def test_wildly_wrong_name_gets_no_suggestions(self, db_session, patch_direct_db_access):
        """A name sharing no real similarity with anything in the catalog
        should not surface unrelated products as 'did you mean' noise."""
        _seed(db_session)
        result = get_product_details("Totally Unrelated Gadget 9000")
        assert "error" in result
        assert "did_you_mean" not in result
