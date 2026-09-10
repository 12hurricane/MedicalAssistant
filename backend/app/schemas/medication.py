from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class MedicationCreate(BaseModel):
    brand_name: str
    generic_name: str
    drug_class: Optional[str] = None
    dosage_form: Optional[str] = None
    standard_strength: Optional[str] = None
    food_interaction_notes: Optional[str] = None

class MedicationUpdate(BaseModel):
    brand_name: Optional[str] = None
    generic_name: Optional[str] = None
    drug_class: Optional[str] = None
    dosage_form: Optional[str] = None
    standard_strength: Optional[str] = None
    food_interaction_notes: Optional[str] = None

class MedicationResponse(BaseModel):
    id: int
    brand_name: str
    generic_name: str
    drug_class: Optional[str] = None
    dosage_form: Optional[str] = None
    standard_strength: Optional[str] = None
    food_interaction_notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
