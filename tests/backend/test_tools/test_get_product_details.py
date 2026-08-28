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
