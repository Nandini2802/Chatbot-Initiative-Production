from typing import Literal

from pydantic import BaseModel, Field, model_validator


ProjectFilterField = Literal[
    "Project_Configuration__c",
    "Service_Charge__c",
    "Construction_Status__c",
    "Anticipated_Handover_Date__c",
    "EOIActive",
    "ProjectSequence",
    "ProjectWebID",
    "Bedrooms_Mob__c",
    "Apartments_Mob__c",
    "Payment_Plan_Mob__c",
    "Completion_Date_Mob__c",
    "Starting_Price_Mob__c",
    "Location_Name_Mob__c",
    "Project_Image__c",
    "UOM__c",
    "Total_Units__c",
    "Total_Sold_Unit__c",
    "Total_Selling_Price__c",
    "Total_Saleable_Area__c",
    "Total_Residential_Units__c",
    "Total_Other_Unit__c",
    "Total_New_Unit__c",
    "Total_Floor__c",
    "Total_Commercial_Units__c",
    "Total_Building__c",
    "Total_Booked_Unit__c",
    "Total_BUA_sq_feet__c",
    "Total_Available_Unit__c",
    "Total_Available_Residential_Units__c",
    "Total_Available_Commercial_Units__c",
    "Plot_Size_Sq_Ft__c",
    "Places_Nearby__c",
    "Building_Type__c",
    "Amenities__c",
    "projectNumber",
    "ProjectName",
    "Id",
    "currency_symbol",
    "is_show_villa",
    "is_visit",
]


ProjectFilterOperator = Literal[
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "contains",
    "not_contains",
    "starts_with",
    "between",
    "is_null",
    "is_not_null",
]


class ProjectFilter(BaseModel):

    field: ProjectFilterField

    operator: ProjectFilterOperator

    value: str | int | float | bool | None = None

    second_value: str | int | float | None = None

    @model_validator(mode="after")
    def validate_filter(self):

        if self.operator in {
            "is_null",
            "is_not_null",
        }:
            return self

        if self.value is None:
            raise ValueError(
                "Filter value is required."
            )

        if (
            isinstance(self.value, str)
            and not self.value.strip()
        ):
            raise ValueError(
                "Filter value cannot be empty."
            )

        if (
            self.operator == "between"
            and self.second_value is None
        ):
            raise ValueError(
                "Between requires two values."
            )

        return self


class ProjectFilterResult(BaseModel):

    filters: list[ProjectFilter] = Field(
        default_factory=list,
        max_length=40,
    )

    logic: Literal["and", "or"] = "and"

    limit: int | None = Field(
        default=None,
        ge=1,
    )

    requires_clarification: bool = False

    clarification_message: str | None = None