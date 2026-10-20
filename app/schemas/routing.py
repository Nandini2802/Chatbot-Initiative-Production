from typing import Literal
from pydantic import BaseModel, Field


IntentType = Literal[
    "marketing",
    "inventory",
    "excel_walkthrough",
    "download_availability",
    "sales_offer",
    "bank_details",
    "project_information",
    "out_of_scope",
]


class RoutingIntent(BaseModel):
    intent: IntentType

    # Original part of the user query
    original_query: str

    # Search-ready version of the request
    expanded_query: str

    # Requested operation
    action: str

    # Extracted entities
    project_name: str | None
    unit_number: str | None

    # Additional filters/parameters
    bedrooms: int | None
    currency: str | None
    file_format: str | None
    bank_account_types: list[str]
    marketing_assets: list[str]

    # Clarification
    missing_fields: list[str]
    requires_clarification: bool


class RoutingResult(BaseModel):
    language: str
    intents: list[RoutingIntent] = Field(min_length=1)
    requires_clarification: bool