"""
Tests for backend.agent.tools.get_solution_content.

Validates the solution narratives loaded from solution_content.json.
"""

from __future__ import annotations

import pytest

from backend.agent.tools.get_solution_content import get_solution_content


class TestGetSolutionContent:
    """get_solution_content should return narratives from the knowledge file."""

    def test_parking_vertical_exists(self):
        """Parking vertical should have a narrative."""
        result = get_solution_content("Parking Payment Systems")
        assert "error" not in result
        assert len(result["narrative"]) > 20
        assert "parking" in result["narrative"].lower()

    def test_transit_vertical_exists(self):
        """Transit vertical should have a narrative."""
        result = get_solution_content("Transit Payment Solutions")
        assert "error" not in result
        assert len(result["narrative"]) > 20
        assert "transit" in result["narrative"].lower()

    def test_retail_vertical_exists(self):
        """Retail vertical should have a narrative."""
        result = get_solution_content("Loyalty Program Contactless Readers")
        assert "error" not in result
        assert len(result["narrative"]) > 20

    def test_vending_vertical_exists(self):
        """Vending vertical should have a narrative."""
        result = get_solution_content("Vending Payment Systems")
        assert "error" not in result
        assert len(result["narrative"]) > 20

    def test_ev_charging_vertical_exists(self):
        """EV charging vertical should have a narrative."""
        result = get_solution_content("EV Charging Station Payment Solutions")
        assert "error" not in result
        assert len(result["narrative"]) > 20

    def test_unknown_vertical_returns_error(self):
        """Unknown vertical should return an error with available vertivals."""
        result = get_solution_content("Unknown Industry")
        assert "error" in result
        assert "available_verticals" in result
        assert len(result["available_verticals"]) > 0

    def test_case_insensitive_fallback(self):
        """Case-insensitive lookup should work."""
        result = get_solution_content("parking payment systems")
        assert "error" not in result
        assert len(result["narrative"]) > 10

    def test_key_differentiators_are_lists(self):
        """Key differentiators should be a list of strings."""
        result = get_solution_content("Parking Payment Systems")
        assert isinstance(result["key_differentiators"], list)
        assert len(result["key_differentiators"]) > 0
        for d in result["key_differentiators"]:
            assert isinstance(d, str)

    def test_all_verticals_have_narratives(self):
        """Every vertical in the knowledge file should have a non-empty narrative."""
        for vertical in [
            "Parking Payment Systems",
            "Transit Payment Solutions",
            "Loyalty Program Contactless Readers",
            "Vending Payment Systems",
            "EV Charging Station Payment Solutions",
        ]:
            result = get_solution_content(vertical)
            assert "error" not in result, f"Vertical '{vertical}' returned error"
            assert len(result["narrative"]) > 20, f"Vertical '{vertical}' has very short narrative"
            assert len(result["key_differentiators"]) > 0, f"Vertical '{vertical}' has no differentiators"
