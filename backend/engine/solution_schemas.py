from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class InstallationDoc(BaseModel):
    title: str
    url: str

class SoftwareRecommendation(BaseModel):
    name: str
    datasheet_url: Optional[str] = None

class HardwareRecommendation(BaseModel):
    name: str
    role: str  # e.g., "Primary Card Reader", "Standalone PIN Pad", "Display", or "All-in-One Terminal"
    technical_specs: Dict[str, Any] = {}
    product_url: Optional[str] = None  # Link to idtechproducts.com product page

class RecommendationBundle(BaseModel):
    hardware_name: str
    hardware_items: List[HardwareRecommendation]
    software: List[SoftwareRecommendation] = []
    highlights: List[str] = []
    explanation: str
    installation_docs: List[InstallationDoc] = []
