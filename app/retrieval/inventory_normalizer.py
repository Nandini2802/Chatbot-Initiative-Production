
from typing import Any

from app.schemas.retrieval import (
    InventoryProject,
    InventoryUnit,
)


def clean_keys(data: dict) -> dict:
    """
    Strip whitespace from API field names only.

    Do not modify the values.
    """
    return {
        str(key).strip(): value
        for key, value in data.items()
    }


def normalize_project(raw: dict) -> InventoryProject:
    data = clean_keys(raw)

    return InventoryProject(
        # Project identification
        project_id=data.get("Id"),
        project_name=data.get("ProjectName"),
        project_number=data.get("projectNumber"),
        project_web_id=data.get("ProjectWebID"),
        project_sequence=data.get("ProjectSequence"),

        # Project configuration
        files=data.get("files"),
        enable_project_for=data.get(
            "Enable_Project_For__c"
        ),
        enable_brandmorph_pitch=data.get(
            "Enable_BrandMorph_Pitch__c"
        ),
        enable_brandmorph_presentation=data.get(
            "Enable_BrandMorph_Presentation__c"
        ),
        project_configuration=data.get(
            "Project_Configuration__c"
        ),
        eoi_active=data.get("EOIActive"),

        # Project details
        service_charge=data.get("Service_Charge__c"),
        construction_status=data.get(
            "Construction_Status__c"
        ),
        handover_date=data.get(
            "Anticipated_Handover_Date__c"
        ),
        completion_date=data.get(
            "Completion_Date_Mob__c"
        ),
        location=data.get(
            "Location_Name_Mob__c"
        ),
        bedrooms_categories=data.get(
            "Bedrooms_Mob__c"
        ),
        apartments=data.get(
            "Apartments_Mob__c"
        ),
        payment_plan=data.get(
            "Payment_Plan_Mob__c"
        ),
        starting_price=data.get(
            "Starting_Price_Mob__c"
        ),
        project_image=data.get(
            "Project_Image__c"
        ),
        unit_of_measurement=data.get("UOM__c"),

        # Unit statistics
        total_units=data.get("Total_Units__c"),
        total_sold_units=data.get(
            "Total_Sold_Unit__c"
        ),
        total_selling_price=data.get(
            "Total_Selling_Price__c"
        ),
        total_saleable_area=data.get(
            "Total_Saleable_Area__c"
        ),
        total_residential_units=data.get(
            "Total_Residential_Units__c"
        ),
        total_other_units=data.get(
            "Total_Other_Unit__c"
        ),
        total_new_units=data.get(
            "Total_New_Unit__c"
        ),
        total_floors=data.get(
            "Total_Floor__c"
        ),
        total_commercial_units=data.get(
            "Total_Commercial_Units__c"
        ),
        total_buildings=data.get(
            "Total_Building__c"
        ),
        total_booked_units=data.get(
            "Total_Booked_Unit__c"
        ),
        total_bua_sqft=data.get(
            "Total_BUA_sq_feet__c"
        ),
        total_available_units=data.get(
            "Total_Available_Unit__c"
        ),
        total_available_residential_units=data.get(
            "Total_Available_Residential_Units__c"
        ),
        total_available_commercial_units=data.get(
            "Total_Available_Commercial_Units__c"
        ),

        # Additional project details
        plot_size_sqft=data.get(
            "Plot_Size_Sq_Ft__c"
        ),
        places_nearby=data.get(
            "Places_Nearby__c"
        ),
        building_type=data.get(
            "Building_Type__c"
        ),
        amenities=data.get("Amenities__c"),

        # Preserve original API data
        attributes=raw.copy(),
    )


def normalize_unit(raw: dict) -> InventoryUnit:
    data = clean_keys(raw)

    return InventoryUnit(
        # Unit identification
        unit_id=data.get("unitId"),
        unit_name=data.get("Name"),
        unit_code=data.get("Unit_Code__c"),

        # Project identification
        project_id=data.get("projectId"),
        project_name=data.get("projectName"),
        project_code=data.get("ProjectCode__c"),
        project_location=data.get("ProjectLocation"),

        # Building details
        building_id=data.get("BuildingID"),
        building_name=data.get("BuildingName"),
        building_code=data.get("BuildingCode__c"),
        floor_number=data.get("FloorNumber__c"),
        floor_code=data.get("Floor_Code__c"),

        # Unit classification
        category=data.get("Category__c"),
        typology=data.get("Typology__c"),
        unit_type=data.get("Unit Type"),
        bedrooms=data.get("NumberOfBedrooms"),
        bathrooms=data.get("NumberOfBathrooms"),
        parking_spaces=data.get("NumberOfCarParks"),

        # Area and property details
        internal_saleable_area=data.get(
            "Internal_Saleable_Area__c"
        ),
        area_sqft=data.get(
            "Total_Saleable_Area_In_Sq_Ft__c"
        ),
        plot_area=data.get("PlotArea__c"),
        view=data.get("View__c"),

        # Pricing
        price=data.get("SellingPrice__c"),
        currency=data.get("currency_symbol"),

        # Status
        status=data.get("Status__c"),
        handover_status=data.get("HandOverStatus"),
        construction_status=data.get(
            "ConstructionStatus"
        ),

        # Additional display flag
        is_show_villa=data.get("is_show_villa"),

        # Preserve original API data
        attributes=raw.copy(),
    )
