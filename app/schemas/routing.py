from typing import Literal
from pydantic import BaseModel, Field
from decimal import Decimal


IntentType = Literal[
    "greeting",
    "thanks",
    "goodbye",
    "acknowledgement",
    "about_assistant",
    "marketing",
    "inventory",
    "excel_walkthrough",
    "download_availability",
    "sales_offer",
    "bank_details",
    "project_information",
    "out_of_scope",
]


# Project facts that can be answered directly (project_operation="field").
# Deliberately excluded: total_available_* (answered by inventory from
# live units), total_selling_price (needs business approval), BrandMorph
# and internal flags.
ProjectFieldName = Literal[
    "project_number",
    "project_code",
    "project_configuration",
    "places_nearby",
    "location",
    "bedrooms_categories",
    "apartments",
    "construction_status",
    "completion_date",
    "handover_date",
    "payment_plan",
    "starting_price",
    "service_charge",
    "amenities",
    "building_type",
    "plot_size_sqft",
    "total_units",
    "total_sold_units",
    "total_booked_units",
    "total_residential_units",
    "total_commercial_units",
    "total_other_units",
    "total_new_units",
    "total_buildings",
    "total_floors",
    "total_bua_sqft",
    "total_saleable_area",
    # Shortcut: "totals for X" -> every total above.
    "all_totals",
]


class RoutingIntent(BaseModel):
    intent: IntentType

    project_reference_source: Literal[
        "explicit",
        "context",
        "none",
        "uncertain",
    ] = "none"

    explicit_project_reference: str | None = None

    feature_name: str | None = None

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

    # Inventory
    inventory_scope: Literal["units", "projects"] | None = None
    min_price: float | None = None
    max_price: float | None = None
    min_area_sqft: float | None = None
    max_area_sqft: float | None = None

    unit_type: str | None = None
    category: str | None = None
    status: str | None = None
    floor_number: str | None = None

    view: str | None = None
    typology: str | None = None
    handover_status: str | None = None
    construction_status: str | None = None
    requires_pool: bool = False
    requires_duplex: bool = False

    project_number: str | None = None
    project_id: str | None = None
    unit_id: str | None = None
    unit_name: str | None = None

    bank_id: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    bank_account_index: int | None = None

    payment_plan_ids: list[str] = Field(default_factory=list)
    payment_plan_numbers: list[int] = Field(default_factory=list)
    offer_id: str | None = None
    project_limit: int | None = None

    project_location: str | None = None

    sort_by: Literal[
        "price_asc",
        "price_desc",
        "area_asc",
        "area_desc",
    ] | None = None

    inventory_operation: Literal[
        "project_info",
        "project_comparison",
        "unit_search",
        "unit_details",
        "unit_comparison",
        "payment_plan",
    ] | None = None

    project_operation: Literal[
        "latest",
        "list",
        "details",
        "location_search",
        "tour",
        "amenities",
        "faq",
        "field",
    ] | None = None

    # Specific project facts requested (project_operation = "field").
    # Only these names are allowed; see app/services/project_fields.py.
    project_fields: list[ProjectFieldName] = Field(
        default_factory=list,
    )

    compare_unit_numbers: list[str] = Field(
        default_factory=list,
    )

    compare_project_names: list[str] = Field(
        default_factory=list,
    )

    


class RoutingResult(BaseModel):
    language: str
    intents: list[RoutingIntent] = Field(min_length=1)
    requires_clarification: bool