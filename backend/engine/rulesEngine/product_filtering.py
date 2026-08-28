from sqlalchemy.orm import Session
from typing import Dict, Any, List
from ...db.repositories.product_query import ProductRepository

def product_filtering(db: Session, constraints: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Search product based on technical constraints and return hardware with software.
    """
    repo = ProductRepository(db)
    
    # 1. Fetch hardware based on constraints
    hardware_list = repo.find_products(
        category=constraints.get("category"),
        use_case=constraints.get("use_case"),
        input_power=constraints.get("input_power"),
        interface=constraints.get("interface"),
        temp=constraints.get("operate_temperature"),
        extra_filter=constraints.get("extra_specs_filter"),
        query=constraints.get("search_query"),
        is_outdoor=constraints.get("is_outdoor"),
        is_standalone=constraints.get("is_standalone")
    )

    # 2. Fallback: If category or use_case was too restrictive, try again without them
    if not hardware_list and (constraints.get("category") or constraints.get("use_case")):
        hardware_list = repo.find_products(
            category=None,
            use_case=None,
            input_power=constraints.get("input_power"),
            interface=constraints.get("interface"),
            temp=constraints.get("operate_temperature"),
            extra_filter=constraints.get("extra_specs_filter"),
            query=constraints.get("search_query"),
            is_outdoor=constraints.get("is_outdoor"),
            is_standalone=constraints.get("is_standalone")
        )

    # 3. Relax extra_specs text filter if still no results.
    if not hardware_list and constraints.get("extra_specs_filter"):
        hardware_list = repo.find_products(
            category=constraints.get("category"),
            use_case=constraints.get("use_case"),
            input_power=constraints.get("input_power"),
            interface=constraints.get("interface"),
            temp=constraints.get("operate_temperature"),
            extra_filter=None,
            query=constraints.get("search_query"),
            is_outdoor=constraints.get("is_outdoor"),
            is_standalone=constraints.get("is_standalone")
        )

    # 4. Relax interface if still no results (common when merchant gives high-level
    # interface needs before exact integration details are known).
    if not hardware_list and constraints.get("interface"):
        hardware_list = repo.find_products(
            category=constraints.get("category"),
            use_case=constraints.get("use_case"),
            input_power=constraints.get("input_power"),
            interface=None,
            temp=constraints.get("operate_temperature"),
            extra_filter=None,
            query=constraints.get("search_query"),
            is_outdoor=constraints.get("is_outdoor"),
            is_standalone=constraints.get("is_standalone")
        )

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

    return results
