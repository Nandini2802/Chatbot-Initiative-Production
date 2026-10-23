import logging


from app.schemas.handler_result import HandlerResult
from app.schemas.retrieval import InventorySnapshot
from app.services.inventory_filter_service import (
    InventoryFilterService,
    norm,
)
from app.services.template_service import TemplateService
from app.services.project_name_service import normalize_project_name


logger = logging.getLogger(__name__)


class InventoryHandler:

    MAX_DISPLAY_UNITS = 20

    def __init__(self, snapshot: InventorySnapshot):
        self.snapshot = snapshot
        self.filter_service = InventoryFilterService()
        self.template_service = TemplateService()

    async def handle(self, intent) -> HandlerResult:

        result = HandlerResult(intent="inventory")

        operation = intent.inventory_operation

        # Project-level inventory
        if (
            intent.intent == "project_information"
            or intent.inventory_scope == "projects"
        ):
            return self._handle_projects(intent, result)

        if intent.inventory_scope != "units":
            result.messages.append(
                "Please specify whether you want "
                "project information or unit details."
            )
            return result

        # Unit comparison
        if operation == "unit_comparison":
            return self._handle_comparison(intent, result)

        # Unit search / details
        if operation == "unit_details" and intent.unit_number:

            requested = norm(intent.unit_number)

            matches = [
                unit
                for unit in self.snapshot.units
                if requested in {
                    norm(unit.unit_name),
                    norm(unit.unit_code),
                    norm(unit.unit_id),
                }
                and (
                    not intent.project_name
                    or normalize_project_name(unit.project_name or "")
                    == normalize_project_name(intent.project_name)
                )
            ]

        else:
            matches = self.filter_service.filter_units(
                units=self.snapshot.units,
                intent=intent,
            )

        if not matches:

            related_units = [
                unit
                for unit in self.snapshot.units
                if (
                    not intent.project_name
                    or normalize_project_name(unit.project_name or "")
                    == normalize_project_name(intent.project_name)
                )
            ]

            result.generation_context = {
                "service": "inventory",
                "operation": operation or "unit_search",
                "match_status": "no_exact_matches",
                "requested_project": intent.project_name,
                "exact_matches": [],
                "related_units": [
                    self._unit_data(unit)
                    for unit in related_units[:5]
                ],
                "related_units_are_not_exact_matches": True,
            }

            result.has_data = True
            return result

        # Unit details require exactly one match.
        if operation == "unit_details" and len(matches) != 1:
            result.messages.append(
                "Multiple units match this identifier. "
                "Please specify the project and exact unit."
            )
            return result

        # Limit the number of displayed units.
        displayed = matches[:self.MAX_DISPLAY_UNITS]

        safe_units = [
            self._unit_data(unit)
            for unit in displayed
        ]

        # STEP 2: Enrich unit details using Active Projects API data.
        if operation == "unit_details" and len(matches) == 1:

            unit = matches[0]

            # Match the project using Salesforce project ID.
            project = next(
                (
                    p for p in self.snapshot.projects
                    if (
                        unit.project_id
                        and p.project_id == unit.project_id
                    )
                ),
                None,
            )

            # Fall back to project-name matching.
            if project is None:
                project = next(
                    (
                        p for p in self.snapshot.projects
                        if normalize_project_name(p.project_name)
                        == normalize_project_name(unit.project_name or "")
                    ),
                    None,
                )

            # Enrich the unit using its matched Active Projects record.
            safe_units[0]["project_information"] = (
                self._project_data(project) if project else None
            )

            logger.debug(
                "INVENTORY_CROSS_API_MATCH | unit=%s | matched=%s",
                unit.unit_name,
                project.project_name if project else None,
            )

        result.generation_context = {
            "service": "inventory",
            "operation": operation or "unit_search",
            "project": intent.project_name,
            "total_matches": len(matches),
            "displayed_count": len(displayed),
            "units": safe_units,
        }

        if operation != "unit_details":

            print(
                "\n========== INVENTORY TEMPLATE DEBUG ==========",
                "\nOperation:", operation,
                "\nTemplate: listing 2.html.j2",
                "\nCard type: inventory_listing",
                "\nUnits displayed:", len(safe_units),
                "\n==============================================",
            )

            result.html_blocks.append({
                "card_type": "inventory_listing",
                "html": self.template_service.render(
                    "listing 2.html.j2",
                    units=safe_units,
                    total_matches=len(matches),
                ),
            })

        result.has_data = True

        return result

    def _handle_projects(self, intent, result):
        projects = self.snapshot.projects

        if intent.project_name:

            requested = normalize_project_name(
                intent.project_name
            )

            projects = [
                project
                for project in projects
                if normalize_project_name(project.project_name or "")
                == requested
            ]

        if not projects:
            result.messages.append(
                "No matching active project information was found."
            )
            return result

        safe_projects = [
            self._project_data(project)
            for project in projects[:20]
        ]

        result.generation_context = {
            "service": "inventory",
            "operation": "project_info",
            "projects": safe_projects,
            "total_matches": len(projects),
        }

        result.has_data = True

        return result

    def _handle_comparison(self, intent, result):

        identifiers = intent.compare_unit_numbers or []

        if len(identifiers) < 2:
            result.messages.append(
                "Please provide at least two unit numbers "
                "to compare."
            )
            return result

        candidates = self.snapshot.units

        if intent.project_name:
            candidates = [
                unit for unit in candidates
                if norm(unit.project_name)
                == norm(intent.project_name)
            ]

        selected = []
        selected_keys = set()

        for identifier in identifiers:

            matches = [
                unit for unit in candidates
                if norm(identifier) in {
                    norm(unit.unit_name),
                    norm(unit.unit_code),
                }
            ]

            if len(matches) != 1:
                result.messages.append(
                    f"Could not uniquely identify unit "
                    f"{identifier} in your visible inventory. "
                    "Please specify its project and unit number."
                )
                return result

            unit = matches[0]
            key = (
                norm(unit.project_name),
                norm(unit.unit_id or unit.unit_name),
            )

            if key in selected_keys:
                result.messages.append(
                    "Please select different units to compare."
                )
                return result

            selected_keys.add(key)
            selected.append(unit)


        safe_units = [
            self._unit_data(unit)
            for unit in selected
        ]

        def display_items(value):
            # Only render simple, verified display values.
            # Complex API structures need explicit field mapping.
            if isinstance(value, str):
                return [value] if value.strip() else []

            if isinstance(value, list):
                return [
                    item.strip()
                    for item in value
                    if isinstance(item, str) and item.strip()
                ]

            return []

        comparisons = []

        for unit, safe_unit in zip(selected, safe_units):
            project = next(
                (
                    p for p in self.snapshot.projects
                    if (
                        unit.project_id
                        and p.project_id == unit.project_id
                    )
                    or (
                        not unit.project_id
                        and norm(p.project_name)
                        == norm(unit.project_name)
                    )
                ),
                None,
            )

            comparisons.append({
                "unit": safe_unit,
                "project": {
                    "project_information": (
                        self._project_data(project) if project else None
                    ),
                    "handover_date": (
                        project.handover_date if project else None
                    ),
                    "amenities": display_items(
                        project.amenities if project else None
                    ),
                    "payment_plans": display_items(
                        project.payment_plan if project else None
                    ),
                },
            })

        result.generation_context = {
            "service": "inventory",
            "operation": "unit_comparison",
            "comparisons": comparisons,
        }

        result.html_blocks.append({
            "card_type": "inventory_comparison",
            "html": self.template_service.render(
                "compare 2.html.j2",
                comparisons=comparisons,
            ),
        })

        result.has_data = True
        return result


    @staticmethod
    def _unit_data(unit):
        return {
            "project_name": unit.project_name,
            "project_code": unit.project_code,
            "project_location": unit.project_location,
            "unit_name": unit.unit_name,
            "unit_code": unit.unit_code,

            "building_name": unit.building_name,
            "building_code": unit.building_code,
            "floor_number": unit.floor_number,
            "floor_code": unit.floor_code,

            "category": unit.category,
            "typology": unit.typology,
            "unit_type": unit.unit_type,

            "bedrooms": unit.bedrooms,
            "bathrooms": unit.bathrooms,
            "parking_spaces": unit.parking_spaces,
            "internal_saleable_area": unit.internal_saleable_area,
            "area_sqft": unit.area_sqft,
            "plot_area": unit.plot_area,
            "view": unit.view,

            "price": unit.price,
            "currency": unit.currency,
            "status": unit.status,
            "handover_status": unit.handover_status,
            "construction_status": unit.construction_status,
            "is_show_villa": unit.is_show_villa,
        }

    @staticmethod
    def _project_data(project):
        """Verified business-facing fields from the Active Projects API.

        Preserve null, zero and false as supplied. Do not expose internal
        Salesforce IDs, feature flags, or potentially authenticated file URLs
        directly to the generation model.
        """
        return {
            "project_name": project.project_name,
            "project_number": project.project_number,
            "project_web_id": project.project_web_id,
            "project_sequence": project.project_sequence,
            "location": project.location,
            "construction_status": project.construction_status,
            "handover_date": project.handover_date,
            "completion_date": project.completion_date,
            "service_charge": project.service_charge,
            "payment_plan": project.payment_plan,
            "starting_price": project.starting_price,
            "bedrooms_categories": project.bedrooms_categories,
            "apartments": project.apartments,
            "project_image": project.project_image,
            "unit_of_measurement": project.unit_of_measurement,
            "total_units": project.total_units,
            "total_sold_units": project.total_sold_units,
            "total_selling_price": project.total_selling_price,
            "total_saleable_area": project.total_saleable_area,
            "total_residential_units": project.total_residential_units,
            "total_other_units": project.total_other_units,
            "total_new_units": project.total_new_units,
            "total_floors": project.total_floors,
            "total_commercial_units": project.total_commercial_units,
            "total_buildings": project.total_buildings,
            "total_booked_units": project.total_booked_units,
            "total_bua_sqft": project.total_bua_sqft,
            "total_available_units": project.total_available_units,
            "total_available_residential_units": (
                project.total_available_residential_units
            ),
            "total_available_commercial_units": (
                project.total_available_commercial_units
            ),
            "plot_size_sqft": project.plot_size_sqft,
            "places_nearby": project.places_nearby,
            "building_type": project.building_type,
            "amenities": project.amenities,
            "eoi_active": project.eoi_active,
        }
