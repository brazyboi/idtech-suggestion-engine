from sqlalchemy.orm import Session
from typing import Dict, Any, List
from ...db.repositories.product_query import ProductRepository

# Constraint keys that the relaxation cascade is allowed to drop. Order matches
# the cascade steps below.
_RELAXABLE_KEYS = ("category", "use_case", "extra_specs_filter", "interface")


def product_filtering(db: Session, constraints: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search product based on technical constraints and return hardware with software.

    If no results are found under the full constraint set, progressively relaxes
    constraints (category+use_case, then extra_specs_filter, then interface) and
    retries. Returns which constraints were actually applied to the result set
    that was returned, and which were dropped along the way, so callers can be
    honest with the end user about relaxation instead of silently presenting a
    relaxed match as an exact one.
    """
    repo = ProductRepository(db)

    def _query(c: Dict[str, Any]):
        return repo.find_products(
            category=c.get("category"),
            use_case=c.get("use_case"),
            input_power=c.get("input_power"),
            interface=c.get("interface"),
            temp=c.get("operate_temperature"),
            extra_filter=c.get("extra_specs_filter"),
            query=c.get("search_query"),
            is_outdoor=c.get("is_outdoor"),
            is_standalone=c.get("is_standalone"),
        )

    requested = {k: v for k, v in constraints.items() if v is not None}
    dropped_keys: List[str] = []

    # 1. Fetch hardware based on constraints
    hardware_list = _query(constraints)

    # 2. Fallback: If category or use_case was too restrictive, try again without them
    if not hardware_list and (constraints.get("category") or constraints.get("use_case")):
        relaxed_constraints = {**constraints, "category": None, "use_case": None}
        hardware_list = _query(relaxed_constraints)
        if hardware_list:
            dropped_keys = [k for k in ("category", "use_case") if k in requested]

    # 3. Relax extra_specs text filter if still no results.
    if not hardware_list and constraints.get("extra_specs_filter"):
        relaxed_constraints = {**constraints, "extra_specs_filter": None}
        hardware_list = _query(relaxed_constraints)
        if hardware_list:
            dropped_keys = ["extra_specs_filter"]

    # 4. Relax interface if still no results (common when merchant gives high-level
    # interface needs before exact integration details are known).
    if not hardware_list and constraints.get("interface"):
        relaxed_constraints = {**constraints, "interface": None, "extra_specs_filter": None}
        hardware_list = _query(relaxed_constraints)
        if hardware_list:
            dropped_keys = [k for k in ("interface", "extra_specs_filter") if k in requested]

    # 5. Format the result into rich JSON for the LLM
    results = []
    for h in hardware_list:
        results.append({
            "hardware_name": h.model_name,
            "compatible_software": [s.name for s in h.software],
            "highlights": [
                f"Power: {h.input_power}",
                f"Interface: {h.interface}",
                f"Temp: {h.operate_temperature}"
            ],
            "technical_specs": {
                "model_name": h.model_name,
                "input_power": h.input_power,
                "interface": h.interface,
                "operate_temperature": h.operate_temperature,
                "ip_rating": h.ip_rating,
                "ik_rating": h.ik_rating,
                "extra_specs": h.extra_specs
            }
        })

    constraints_relaxed = {k: v for k, v in requested.items() if k in dropped_keys}
    constraints_applied = {k: v for k, v in requested.items() if k not in dropped_keys}

    return {
        "products": results,
        "constraints_applied": constraints_applied,
        "constraints_relaxed": constraints_relaxed,
    }
