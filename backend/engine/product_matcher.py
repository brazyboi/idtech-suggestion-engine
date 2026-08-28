"""
Product matching and recommendation bundle building.

Responsible for:
- Running product_filtering queries against the database
- Building RecommendationBundle objects from result rows
- Fetching installation documentation
- Debug/match tracing
"""

import os
from typing import Any, Dict, List, Optional, Tuple

from ..db.session import SessionLocal
from ..engine.rulesEngine.product_filtering import product_filtering
from ..engine.solution_schemas import (
    HardwareRecommendation,
    InstallationDoc,
    RecommendationBundle,
)
from ..engine.state_machine import CollectedInfo


class ProductMatcher:
    """
    Runs product matching queries and builds recommendation bundles.
    Owns no state — all methods are static/stateless.
    """

    DEBUG_MATCH_ENV = "CHAT_DEBUG_MATCH"

    @staticmethod
    def _debug_match_enabled() -> bool:
        return os.getenv(ProductMatcher.DEBUG_MATCH_ENV, "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _build_debug_match_payload(
        constraints: Dict[str, Any],
        rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "constraints": constraints,
            "rows_returned": len(rows),
            "top_candidates": [r.get("hardware_name") for r in rows[:5]],
        }

    @staticmethod
    def match(collected: CollectedInfo) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        Run the product matching query against the database.

        Returns:
            (rows, constraints, debug_payload)
        """
        constraints = collected.to_flat_constraints()
        db = SessionLocal()
        try:
            rows = product_filtering(db, constraints)
        finally:
            db.close()

        debug_match = (
            ProductMatcher._build_debug_match_payload(constraints, rows)
            if ProductMatcher._debug_match_enabled()
            else None
        )
        return rows, constraints, debug_match

    @staticmethod
    def build_recommendation_bundle(
        rows: List[Dict[str, Any]],
        constraints: Dict[str, Any],
    ) -> RecommendationBundle:
        """Deterministically build a recommendation bundle from product data."""
        items = []
        for row in rows[:3]:
            specs = row.get("technical_specs", {})
            items.append(HardwareRecommendation(
                name=row.get("hardware_name", specs.get("model_name", "Unknown")),
                role="Primary Card Reader",
                technical_specs=specs,
            ))

        if not items:
            return RecommendationBundle(
                hardware_name="",
                hardware_items=[],
                explanation="No matching products found.",
            )

        top = rows[0]
        specs = top.get("technical_specs", {})

        evidence_parts = []
        for field, label in [
            ("input_power", "power"),
            ("interface", "interface"),
            ("operate_temperature", "temp range"),
            ("ip_rating", "IP rating"),
        ]:
            val = specs.get(field)
            if val:
                evidence_parts.append(f"{label}: {val}")

        extras = str(specs.get("extra_specs", "")).lower()
        if "display" in extras:
            evidence_parts.append("built-in display")
        if "pin" in extras or "keypad" in extras:
            evidence_parts.append("PIN entry support")
        if "weather" in extras or "ip" in extras:
            evidence_parts.append("weatherproof design")

        if not evidence_parts:
            evidence_parts.append("compatibility match")

        explanation = (
            f"Based on your requirements, I recommend the {items[0].name}. "
            f"It matches on: {', '.join(evidence_parts)}. "
            f"This device is suitable for your deployment needs."
        )

        highlights = []
        for label, field in [
            ("Power", "input_power"),
            ("Interface", "interface"),
            ("Temperature Range", "operate_temperature"),
            ("Weather Rating", "ip_rating"),
        ]:
            val = specs.get(field)
            if val:
                highlights.append(f"{label}: {val}")

        docs = ProductMatcher._fetch_installation_docs(items[0].name) if items else []

        return RecommendationBundle(
            hardware_name=items[0].name,
            hardware_items=items,
            software=[],
            highlights=highlights,
            explanation=explanation,
            installation_docs=docs,
        )

    @staticmethod
    def _fetch_installation_docs(model_name: str) -> List[InstallationDoc]:
        try:
            from ..engine.doc_fetcher import fetch_installation_docs
            result = fetch_installation_docs(model_name)
            if result:
                return [InstallationDoc(**doc) for doc in result]
        except Exception:
            pass
        return []
