from pydantic import BaseModel
from typing import Any, Dict, Optional


class RawPayload(BaseModel):
    """
    Accepts any key-value pairs the client sends.
    All values are treated as strings initially.
    """
    model_config = {"extra": "allow"}

    # Make every field optional so truly arbitrary keys are accepted
    # (FastAPI / Pydantic v2 will put unknown keys in model_extra)


class MappingResult(BaseModel):
    """What OpenAI returns after semantic field mapping."""
    mapped: Dict[str, str]           # valid_field -> client_value  (only matched)
    unmatched: Dict[str, str]        # client_field -> reason it was rejected


class UserResponse(BaseModel):
    """Final API response sent back to the client."""
    success: bool
    message: str
    original_payload: Dict[str, Any]
    mapped_payload: Optional[Dict[str, str]] = None
    saved_record: Optional[Dict[str, Any]]   = None
    unmatched_fields: Optional[Dict[str, str]] = None
