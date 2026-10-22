
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class InventoryBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )


class InventoryProject(InventoryBaseModel):
    # Project identification
    project_id: str | None = None
    project_name: str | None = None
    project_number: Any = None
    project_web_id: Any = None
    project_sequence: Any = None

    # Project configuration
    files: Any = None
    enable_project_for: Any = None
    enable_brandmorph_pitch: Any = None
    enable_brandmorph_presentation: Any = None
    project_configuration: Any = None
    eoi_active: Any = None

    # Project details
    service_charge: Any = None
    construction_status: Any = None
    handover_date: Any = None
    completion_date: Any = None
    location: Any = None
    bedrooms_categories: Any = None
    apartments: Any = None
    payment_plan: Any = None
    starting_price: Any = None
    project_image: Any = None
    unit_of_measurement: Any = None

    # Unit statistics
    total_units: Any = None
    total_sold_units: Any = None
    total_selling_price: Any = None
    total_saleable_area: Any = None
    total_residential_units: Any = None
    total_other_units: Any = None
    total_new_units: Any = None
    total_floors: Any = None
    total_commercial_units: Any = None
    total_buildings: Any = None
    total_booked_units: Any = None
    total_bua_sqft: Any = None
    total_available_units: Any = None
    total_available_residential_units: Any = None
    total_available_commercial_units: Any = None

    # Additional project details
    plot_size_sqft: Any = None
    places_nearby: Any = None
    building_type: Any = None
    amenities: Any = None

    # Original API record, unchanged
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        exclude=True,
    )


class InventoryUnit(InventoryBaseModel):
    # Unit identification
    unit_id: str | None = None
    unit_name: str | None = None
    unit_code: Any = None

    # Project identification
    project_id: str | None = None
    project_name: str | None = None
    project_code: Any = None
    project_location: Any = None

    # Building details
    building_id: Any = None
    building_name: Any = None
    building_code: Any = None
    floor_number: Any = None
    floor_code: Any = None

    # Unit classification
    category: Any = None
    typology: Any = None
    unit_type: Any = None
    bedrooms: Any = None
    bathrooms: Any = None
    parking_spaces: Any = None

    # Area and property details
    internal_saleable_area: Any = None
    area_sqft: Any = None
    plot_area: Any = None
    view: Any = None

    # Pricing
    price: Any = None
    currency: Any = None

    # Status
    status: Any = None
    handover_status: Any = None
    construction_status: Any = None

    # Additional display flag
    is_show_villa: Any = None

    # Original API record, unchanged
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        exclude=True,
    )


class InventorySnapshot(BaseModel):
    projects: list[InventoryProject] = Field(
        default_factory=list
    )
    units: list[InventoryUnit] = Field(
        default_factory=list
    )
