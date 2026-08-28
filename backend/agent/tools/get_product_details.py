"""
get_product_details tool — wraps ProductMatcher + DocFetcher.

Returns full specs, compatible software, installation docs, and highlights
for a specific hardware product by model name.
"""

from typing import Any, Dict, List, Optional

from ...db.session import SessionLocal
from ...db.repositories.product_query import ProductRepository
from ...engine.product_matcher import ProductMatcher
from ._product_url import get_product_url


def get_product_details(model_name: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific hardware product.

    Returns a dict with:
        - model_name: the product name
        - technical_specs: full specifications
        - compatible_software: software that works with this hardware
        - categories: product categories
        - use_cases: applicable use cases
        - installation_docs: links to installation documentation
        - highlights: human-readable key features
    """
    db = SessionLocal()
    try:
        repo = ProductRepository(db)
        # Use find_products with query to locate the specific model
        rows = repo.find_products(query=model_name)
        if not rows:
            return {"error": f"No product found matching '{model_name}'."}

        # Find exact match
        matching = None
        for hw in rows:
            if hw.model_name.lower() == model_name.lower():
                matching = hw
                break
        if not matching:
            matching = rows[0]  # Fall back to first result

        specs = {
            "model_name": matching.model_name,
            "input_power": matching.input_power,
            "interface": matching.interface,
            "operate_temperature": matching.operate_temperature,
            "ip_rating": matching.ip_rating,
            "ik_rating": matching.ik_rating,
            "extra_specs": matching.extra_specs,
        }

        software_names = [s.name for s in matching.software]
        category_names = [c.name for c in matching.categories]
        use_case_names = [u.name for u in matching.use_cases]

        # Build highlights
        highlights = []
        for label, field in [
            ("Power", "input_power"),
            ("Interface", "interface"),
            ("Temperature Range", "operate_temperature"),
            ("Weather Rating", "ip_rating"),
        ]:
            val = getattr(matching, field, None)
            if val:
                highlights.append(f"{label}: {val}")

        ext = str(matching.extra_specs or "").lower()
        if "display" in ext:
            highlights.append("Built-in display")
        if "pin" in ext or "keypad" in ext:
            highlights.append("PIN entry support")
        if "weather" in ext:
            highlights.append("Weatherproof design")

        # Fetch installation docs
        docs: List[Dict[str, str]] = []
        try:
            fetched = ProductMatcher._fetch_installation_docs(matching.model_name)
            if fetched:
                docs = [{"title": d.title, "url": d.url} for d in fetched]
        except Exception:
            pass

        # Build software with datasheet URLs from extra_fields if available
        software_with_urls: List[Dict[str, Any]] = []
        for sw_name in software_names:
            entry: Dict[str, Any] = {"name": sw_name}
            # Look up datasheet from software extra_fields
            for sw in matching.software:
                if sw.name == sw_name and sw.extra_fields:
                    url = sw.extra_fields.get("datasheet_url") or sw.extra_fields.get("product_url")
                    if url:
                        entry["datasheet_url"] = url
                    break
            software_with_urls.append(entry)

        return {
            "model_name": matching.model_name,
            "product_url": get_product_url(matching.model_name),
            "technical_specs": specs,
            "compatible_software": software_with_urls,
            "categories": category_names,
            "use_cases": use_case_names,
            "highlights": highlights,
            "installation_docs": docs,
        }
    finally:
        db.close()
