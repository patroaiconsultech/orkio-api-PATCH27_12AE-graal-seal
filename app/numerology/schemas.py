from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class NumerologyProfileIn(BaseModel):
    full_name: str = Field(min_length=2)
    birth_date: str = Field(min_length=8, description="YYYY-MM-DD")
    preferred_name: Optional[str] = None
    context: Optional[str] = None
    consent: bool = False

class NumerologyProfileOut(BaseModel):
    profile_type: str
    confidence_level: str
    user_confirmed: bool
    dimensions: Dict[str, Any]
    narrative_summary: str
    practical_guidance: List[str]
    planner_hints: Dict[str, Any]
    metadata: Dict[str, Any]
