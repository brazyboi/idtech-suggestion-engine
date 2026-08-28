"""
Tests for backend.db.repositories.admin_repository.AdminRepository.

This repository backs every maintenance/admin CRUD endpoint (hardware,
categories, use cases, software) and had zero test coverage before this
file existed, despite being one of the most-connected modules in the
codebase. Runs against an in-memory SQLite DB (see conftest.db_session).
"""

import pytest

from backend.db.repositories.admin_repository import (
    AdminRepository,
    DuplicateError,
    NotFoundError,
    UnknownReferenceError,
)


@pytest.fixture
def repo(db_session):
    return AdminRepository(db_session)


# ── Hardware: create ─────────────────────────────────────────────────

class TestCreateHardware:
    def test_creates_hardware_with_no_references(self, repo):
        hw = repo.create_hardware(
            model_name="VP3300",
            fields={"input_power": "USB", "interface": "USB"},
            categories=[],
            use_cases=[],
            software=[],
        )
        assert hw.id is not None
        assert hw.model_name == "VP3300"
        assert hw.input_power == "USB"
        assert hw.is_active is True

    def test_creates_hardware_with_resolved_references(self, repo):
        repo.create_category("Retail")
        repo.create_use_case("Vending")
        repo.create_software("IDTECH IDPar")

        hw = repo.create_hardware(
            model_name="VP3300",
            fields={},
            categories=["Retail"],
            use_cases=["Vending"],
            software=["IDTECH IDPar"],
        )
        assert [c.name for c in hw.categories] == ["Retail"]
        assert [u.name for u in hw.use_cases] == ["Vending"]
        assert [s.name for s in hw.software] == ["IDTECH IDPar"]

    def test_rejects_duplicate_model_name(self, repo):
        repo.create_hardware(model_name="VP3300", fields={}, categories=[], use_cases=[], software=[])
        with pytest.raises(DuplicateError):
            repo.create_hardware(model_name="VP3300", fields={}, categories=[], use_cases=[], software=[])

    def test_rejects_unknown_category_reference(self, repo):
        with pytest.raises(UnknownReferenceError) as exc_info:
            repo.create_hardware(
                model_name="VP3300", fields={}, categories=["Nonexistent"], use_cases=[], software=[],
            )
        assert exc_info.value.kind == "category"
        assert "Nonexistent" in exc_info.value.missing

    def test_only_known_hardware_fields_are_applied(self, repo):
        """Arbitrary keys in `fields` must be silently ignored, not raise or leak in."""
        hw = repo.create_hardware(
            model_name="VP3300",
            fields={"input_power": "USB", "not_a_real_column": "danger"},
            categories=[],
            use_cases=[],
            software=[],
        )
        assert not hasattr(hw, "not_a_real_column")


# ── Hardware: read ───────────────────────────────────────────────────

class TestReadHardware:
    def test_get_hardware_returns_none_when_missing(self, repo):
        assert repo.get_hardware("does-not-exist") is None

    def test_get_hardware_excludes_soft_deleted(self, repo):
        repo.create_hardware(model_name="VP3300", fields={}, categories=[], use_cases=[], software=[])
        repo.soft_delete_hardware("VP3300")
        assert repo.get_hardware("VP3300") is None
        # ...but it's still there if you explicitly ask for inactive rows too
        assert repo.get_hardware_including_inactive("VP3300") is not None

    def test_list_hardware_excludes_soft_deleted(self, repo):
        repo.create_hardware(model_name="VP3300", fields={}, categories=[], use_cases=[], software=[])
        repo.create_hardware(model_name="VP5300", fields={}, categories=[], use_cases=[], software=[])
        repo.soft_delete_hardware("VP3300")

        names = [h.model_name for h in repo.list_hardware()]
        assert names == ["VP5300"]


# ── Hardware: update ─────────────────────────────────────────────────

class TestUpdateHardware:
    def test_updates_fields_in_place(self, repo):
        repo.create_hardware(model_name="VP3300", fields={"input_power": "USB"}, categories=[], use_cases=[], software=[])
        updated = repo.update_hardware("VP3300", fields={"input_power": "VAC"})
        assert updated.input_power == "VAC"

    def test_rename_to_available_name_succeeds(self, repo):
        repo.create_hardware(model_name="VP3300", fields={}, categories=[], use_cases=[], software=[])
        updated = repo.update_hardware("VP3300", new_model_name="VP3300-A")
        assert updated.model_name == "VP3300-A"
        assert repo.get_hardware("VP3300") is None

    def test_rename_to_existing_name_raises_duplicate(self, repo):
        repo.create_hardware(model_name="VP3300", fields={}, categories=[], use_cases=[], software=[])
        repo.create_hardware(model_name="VP5300", fields={}, categories=[], use_cases=[], software=[])
        with pytest.raises(DuplicateError):
            repo.update_hardware("VP3300", new_model_name="VP5300")

    def test_update_missing_hardware_raises_not_found(self, repo):
        with pytest.raises(NotFoundError):
            repo.update_hardware("does-not-exist", fields={"input_power": "USB"})

    def test_update_replaces_references(self, repo):
        repo.create_category("Retail")
        repo.create_category("Parking")
        repo.create_hardware(model_name="VP3300", fields={}, categories=["Retail"], use_cases=[], software=[])

        updated = repo.update_hardware("VP3300", categories=["Parking"])
        assert [c.name for c in updated.categories] == ["Parking"]


# ── Hardware: soft delete ────────────────────────────────────────────

class TestSoftDeleteHardware:
    def test_soft_delete_marks_inactive_without_removing_row(self, repo, db_session):
        repo.create_hardware(model_name="VP3300", fields={}, categories=[], use_cases=[], software=[])
        repo.soft_delete_hardware("VP3300")

        hw = repo.get_hardware_including_inactive("VP3300")
        assert hw is not None
        assert hw.is_active is False

    def test_soft_delete_missing_hardware_raises_not_found(self, repo):
        with pytest.raises(NotFoundError):
            repo.soft_delete_hardware("does-not-exist")


# ── Reference tables (category/use_case/software): create/rename/delete ──

class TestReferenceTableLifecycle:
    def test_create_rejects_blank_name(self, repo):
        with pytest.raises(ValueError):
            repo.create_category("   ")

    def test_create_is_case_insensitive_duplicate_check(self, repo):
        repo.create_category("Retail")
        with pytest.raises(DuplicateError):
            repo.create_category("retail")

    def test_rename_to_same_name_different_case_is_a_noop(self, repo):
        cat = repo.create_category("Retail")
        renamed = repo.rename_category("Retail", "RETAIL")
        assert renamed.id == cat.id

    def test_rename_collision_raises_duplicate(self, repo):
        repo.create_category("Retail")
        repo.create_category("Parking")
        with pytest.raises(DuplicateError):
            repo.rename_category("Parking", "Retail")

    def test_rename_missing_raises_not_found(self, repo):
        with pytest.raises(NotFoundError):
            repo.rename_category("does-not-exist", "New Name")

    def test_delete_removes_row(self, repo):
        repo.create_use_case("Vending")
        repo.delete_use_case("Vending")
        assert repo.list_use_cases() == []

    def test_delete_missing_raises_not_found(self, repo):
        with pytest.raises(NotFoundError):
            repo.delete_software("does-not-exist")


# ── Software extra_fields ────────────────────────────────────────────

class TestSoftwareExtraFields:
    def test_create_software_with_extra_fields(self, repo):
        sw = repo.create_software_with_extra_fields("IDPar", extra_fields={"datasheet_url": "https://x"})
        assert sw.extra_fields == {"datasheet_url": "https://x"}

    def test_update_software_merges_extra_fields(self, repo):
        repo.create_software_with_extra_fields("IDPar", extra_fields={"a": "1"})
        updated = repo.update_software("IDPar", extra_fields={"b": "2"})
        assert updated.extra_fields == {"a": "1", "b": "2"}

    def test_delete_extra_field_removes_only_that_key(self, repo):
        repo.create_software_with_extra_fields("IDPar", extra_fields={"a": "1", "b": "2"})
        updated = repo.delete_software_extra_field("IDPar", "a")
        assert updated.extra_fields == {"b": "2"}

    def test_delete_missing_extra_field_raises_not_found(self, repo):
        repo.create_software_with_extra_fields("IDPar", extra_fields={"a": "1"})
        with pytest.raises(NotFoundError):
            repo.delete_software_extra_field("IDPar", "does-not-exist")
