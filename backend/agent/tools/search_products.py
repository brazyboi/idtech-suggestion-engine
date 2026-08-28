"""
search_products tool — wraps ProductRepository.find_products() + product_filtering().

Accepts constraint parameters from the LLM, queries the database,
and returns matching hardware with key specs. No pricing data is exposed.
"""

from typing import Any, Dict, List

from ...db.session import SessionLocal
from ...engine.rulesEngine.product_filtering import product_filtering
from ._product_url import get_product_url


def search_products(
    use_case: str | None = None,
    category: str | None = None,
    input_power: str | None = None,
    interface: str | None = None,
    is_outdoor: bool | None = None,
    is_standalone: bool | None = None,
    extra_tags: str | None = None,
    query: str | None = None,
) -> Dict[str, Any]:
    """
    Search the product catalog for matching hardware.

    Returns a dict with:
        - products: list of matching hardware items
        - count: number of results
        - constraints_used: the constraints that were applied
    """
    constraints: Dict[str, Any] = {}
    if use_case:
        constraints["use_case"] = use_case
    if category:
        constraints["category"] = category
    if input_power:
        constraints["input_power"] = input_power
    if interface:
        constraints["interface"] = interface
    if is_outdoor:
        constraints["is_outdoor"] = True
    if is_standalone:
        constraints["is_standalone"] = True
    if extra_tags:
        constraints["extra_specs_filter"] = extra_tags
    if query:
        constraints["search_query"] = query

    db = SessionLocal()
    try:
        rows = product_filtering(db, constraints)
    finally:
        db.close()

    # Strip down to LLM-safe fields — no pricing, no internal IDs
    products = []
    for row in rows[:5]:  # Return top 5 to avoid flooding context
        specs = row.get("technical_specs", {})
        model_name = row.get("hardware_name", specs.get("model_name", "Unknown"))
        products.append({
            "model_name": model_name,
            "product_url": get_product_url(model_name),
            "compatible_software": row.get("compatible_software", []),
            "highlights": row.get("highlights", []),
            "key_specs": {
                "input_power": specs.get("input_power"),
                "interface": specs.get("interface"),
                "operate_temperature": specs.get("operate_temperature"),
                "ip_rating": specs.get("ip_rating"),
                "ik_rating": specs.get("ik_rating"),
            },
        })

    return {
        "products": products,
        "count": len(products),
        "constraints_used": {k: v for k, v in constraints.items() if v is not None},
    }
