from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class InventoryFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_location: str | None = None
    view: str | None = None
    typology: str | None = None
    unit_type: str | None = None
    category: str | None = None
    status: str | None = None
    handover_status: str | None = None
    construction_status: str | None = None

    bedrooms: int | None = Field(default=None, ge=0)
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    min_area_sqft: float | None = Field(default=None, ge=0)
    max_area_sqft: float | None = Field(default=None, ge=0)
    currency: str | None = None

    sort_by: Literal[
        "price_asc",
        "price_desc",
        "area_asc",
        "area_desc",
    ] | None = None

    requires_pool: bool = False
    requires_duplex: bool = False

    unresolved_terms: list[str] = Field(default_factory=list)