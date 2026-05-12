from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class HardwareBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    operate_temperature: Optional[str] = None
    input_power: Optional[str] = None
    ip_rating: Optional[str] = None
    ik_rating: Optional[str] = None
    interface: Optional[str] = None
    extra_specs: Optional[Dict[str, Any]] = None
    categories: List[str] = Field(default_factory=list)
    use_cases: List[str] = Field(default_factory=list)
    software: List[str] = Field(default_factory=list)


class HardwareCreate(HardwareBase):
    model_name: str


class HardwareUpdate(BaseModel):
    # Only provided fields are updated, arrays are replaced not merged
    model_config = ConfigDict(protected_namespaces=())

    model_name: Optional[str] = None
    operate_temperature: Optional[str] = None
    input_power: Optional[str] = None
    ip_rating: Optional[str] = None
    ik_rating: Optional[str] = None
    interface: Optional[str] = None
    extra_specs: Optional[Dict[str, Any]] = None
    categories: Optional[List[str]] = None
    use_cases: Optional[List[str]] = None
    software: Optional[List[str]] = None


class HardwareOut(HardwareBase):
    id: int
    model_name: str
    is_active: bool


class HardwareSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    model_name: str
    is_active: bool


class ReferenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    name: str


class ReferenceCreate(BaseModel):
    name: str
