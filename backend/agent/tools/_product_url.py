"""
Product URL builder — constructs links to ID TECH website product pages.

Uses IDTECH_PRODUCT_BASE_URL env var with a sensible default.
Model names are slugified: spaces → hyphens, lowercase, no special chars.

Examples:
    VP3300     → https://idtechproducts.com/product/vp3300/
    MiniMag II → https://idtechproducts.com/product/minimag-ii/
"""

import os
import re
from typing import Optional


_IDTECH_BASE = os.getenv(
    "IDTECH_PRODUCT_BASE_URL",
    "https://idtechproducts.com",
)


def get_product_url(model_name: str) -> Optional[str]:
    """
    Build the product page URL for a given model name.

    Returns None if model_name is empty/falsy.
    """
    if not model_name or not model_name.strip():
        return None

    # Slugify: lowercase, spaces → hyphens, strip non-alphanumeric except hyphens
    slug = model_name.strip().lower()
    slug = slug.replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug)  # Collapse multiple hyphens
    slug = slug.strip("-")  # Remove leading/trailing hyphens

    if not slug:
        return None

    return f"{_IDTECH_BASE}/products/{slug}/"
