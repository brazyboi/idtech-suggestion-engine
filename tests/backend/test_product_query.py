"""
Tests for backend.db.repositories.product_query.ProductRepository.find_products.

This is the core hardware-matching engine behind the agent's search_products
tool — the thing sponsors will judge the chatbot's recommendation quality by.
It had zero test coverage before this file existed. Runs against an
in-memory SQLite DB (see conftest.db_session).
"""

import pytest

from backend.db.repositories.admin_repository import AdminRepository
from backend.db.repositories.product_query import ProductRepository
from backend.agent.tools.search_products import search_products


@pytest.fixture
def admin(db_session):
    return AdminRepository(db_session)


@pytest.fixture
def query(db_session):
    return ProductRepository(db_session)


@pytest.fixture
def seeded(admin):
    """Two hardware rows spanning distinct power/interface/category combos."""
    admin.create_category("Retail")
    admin.create_category("Parking")
    admin.create_use_case("Vending")

    usb_indoor = admin.create_hardware(
        model_name="VP3300",
        fields={
            "input_power": "USB",
            "interface": "USB",
            "operate_temperature": "0C to 40C",
            "ip_rating": None,
            "extra_specs": {"note": "compact desktop reader"},
        },
        categories=["Retail"],
        use_cases=[],
        software=[],
    )
    vac_outdoor = admin.create_hardware(
        model_name="VP5300",
        fields={
            "input_power": "24VAC",
            "interface": "RS232",
            "operate_temperature": "-20C to 65C",
            "ip_rating": "IP65",
            "extra_specs": {"note": "weatherproof standalone unit with keypad, CPU, RAM"},
        },
        categories=["Parking"],
        use_cases=["Vending"],
        software=[],
    )
    return usb_indoor, vac_outdoor


class TestFindProductsFiltering:
    def test_no_constraints_returns_everything(self, query, seeded):
        results = query.find_products()
        assert {h.model_name for h in results} == {"VP3300", "VP5300"}

    def test_filters_by_category(self, query, seeded):
        results = query.find_products(category="Retail")
        assert [h.model_name for h in results] == ["VP3300"]

    def test_filters_by_use_case(self, query, seeded):
        results = query.find_products(use_case="Vending")
        assert [h.model_name for h in results] == ["VP5300"]

    def test_filters_by_exact_search_query(self, query, seeded):
        results = query.find_products(query="VP5300")
        assert [h.model_name for h in results] == ["VP5300"]

    def test_ac_power_query_matches_vac_synonym(self, query, seeded):
        """'AC' should match a device whose input_power is '24VAC' via the VAC/AC synonym rule."""
        results = query.find_products(input_power="AC")
        names = {h.model_name for h in results}
        assert "VP5300" in names

    def test_is_outdoor_matches_ip_rated_device(self, query, seeded):
        results = query.find_products(is_outdoor=True)
        names = {h.model_name for h in results}
        assert "VP5300" in names
        assert "VP3300" not in names

    def test_is_standalone_matches_device_with_cpu_keywords(self, query, seeded):
        results = query.find_products(is_standalone=True)
        names = {h.model_name for h in results}
        assert "VP5300" in names
        assert "VP3300" not in names

    def test_extra_filter_pin_matches_keypad_synonym(self, query, seeded):
        """extra_specs_filter='PIN' should match a device tagged 'keypad' via synonym mapping."""
        results = query.find_products(extra_filter="PIN")
        names = {h.model_name for h in results}
        assert "VP5300" in names

    def test_no_match_returns_empty_not_error(self, query, seeded):
        results = query.find_products(query="ThisModelDoesNotExist")
        assert results == []

    def test_combining_contradictory_filters_returns_empty(self, query, seeded):
        results = query.find_products(category="Retail", use_case="Vending")
        assert results == []


class TestConstraintRelaxationReporting:
    """The fallback cascade must report exactly which constraints it dropped."""

    def test_unknown_category_is_reported_as_relaxed(self, patch_direct_db_access, seeded):
        result = search_products(category="card reader")

        assert result["products"]
        assert result["constraints_applied"] == {}
        assert result["constraints_relaxed"] == {"category": "card reader"}
        assert "constraints_used" not in result

    def test_exact_match_has_no_false_relaxation(self, patch_direct_db_access, seeded):
        result = search_products(category="Parking")

        assert [product["model_name"] for product in result["products"]] == ["VP5300"]
        assert result["constraints_applied"] == {"category": "Parking"}
        assert result["constraints_relaxed"] == {}

    def test_use_case_relaxation_preserves_other_applied_constraints(
        self, patch_direct_db_access, seeded
    ):
        result = search_products(use_case="Vending", interface="USB")

        assert [product["model_name"] for product in result["products"]] == ["VP3300"]
        assert result["constraints_applied"] == {"interface": "USB"}
        assert result["constraints_relaxed"] == {"use_case": "Vending"}
