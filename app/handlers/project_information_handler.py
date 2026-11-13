
import asyncio
import logging
import re

from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

from app.core.keyvault import load_application_secrets
from app.schemas.handler_result import HandlerResult

from app.retrieval.project_information_connector import (
    ProjectInformationConnector,
    ProjectInformationAPIError,
)

from app.retrieval.project_coordinates_connector import (
    ProjectCoordinatesConnector,
)

from app.retrieval.osf_portfolio_connector import (
    OSFPortfolioConnector,
)

from app.services.template_service import TemplateService

from app.utils.google_maps import (
    normalize_map_project_name,
    generate_map_url_from_coordinates,
)

from app.utils.project_tours import (
    build_project_tour_lookup,
)

from app.utils.project_faqs import (
    extract_project_faqs,
)

from app.services.project_fields import (
    build_field_answer,
    expand_fields,
    field_rows,
)

from app.retrieval.construction_update_connector import (
    ConstructionUpdateConnector,
)


logger = logging.getLogger(__name__)


def normalize(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").casefold(),
    )


class ImageURLParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.urls = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a" and attrs.get("href"):
            self.urls.append(attrs["href"])

        if tag == "img" and attrs.get("src"):
            self.urls.append(attrs["src"])

    def handle_data(self, data):
        self.text.append(data)


def safe_image_url(value):

    if not isinstance(value, str) or not value.strip():
        return None

    parser = ImageURLParser()
    parser.feed(value)

    candidates = (
        parser.urls
        + ["".join(parser.text).strip()]
        + [value.strip()]
    )

    allowed_hosts = {
        "danubeproperties.com",
        "www.danubeproperties.com",
    }

    allowed_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
    }

    for candidate in candidates:

        url = unescape(candidate).strip()
        parsed = urlparse(url)

        if (
            parsed.scheme != "https"
            or parsed.hostname not in allowed_hosts
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            continue

        if not parsed.path.lower().endswith(
            tuple(allowed_extensions)
        ):
            continue

        return url

    return None


def safe_amenity_image_url(value):
    """
    Validate amenity images returned by OSF Portfolio API.

    Supports HTTPS image URLs hosted on approved
    Danube Properties domains, including staging.
    """

    if not isinstance(value, str):
        return None

    url = unescape(value).strip()

    if not url:
        return None

    try:
        parsed = urlparse(url)

        hostname = (parsed.hostname or "").lower()

        allowed_domain = (
            hostname == "danubeproperties.com"
            or hostname.endswith(".danubeproperties.com")
        )

        if not allowed_domain:
            return None

        if parsed.scheme != "https":
            return None

        if parsed.username or parsed.password:
            return None

        if parsed.port not in (None, 443):
            return None

        allowed_extensions = (
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".gif",
        )

        if not parsed.path.lower().endswith(
            allowed_extensions
        ):
            return None

        return url

    except ValueError:
        return None


class ProjectInformationHandler:

    def __init__(
        self,
        *,
        inventory_snapshot,
        inventory_token: str,
        access_token: str,
    ):

        self.snapshot = inventory_snapshot
        self.inventory_token = inventory_token
        self.access_token = access_token

        # Existing project information API.
        self.connector = ProjectInformationConnector()

        # NEW: Project coordinates API.
        # Uses project_id to retrieve latitude/longitude.
        self.coordinates_connector = (
            ProjectCoordinatesConnector()
        )

        # KEEP: OSF Portfolio API for 3D tours.
        self.tour_connector = OSFPortfolioConnector()

        self.construction_connector = ConstructionUpdateConnector()

        self.templates = TemplateService()


    def failure(self, message):

        return HandlerResult(
            intent="project_information",
            messages=[message],
            has_data=False,
        )

    def resolve_project(self, intent, projects):

        identifiers = [
            ("project_id", intent.project_id),
            ("project_number", intent.project_number),
            ("project_name", intent.project_name),
        ]

        candidate_sets = []

        for field, value in identifiers:

            if not value:
                continue

            key = normalize(value)

            exact = [
                project
                for project in projects
                if normalize(
                    getattr(project, field, None)
                ) == key
            ]

            # Permit unique shortened project names.
            if not exact and field == "project_name":

                exact = [
                    project
                    for project in projects
                    if key in normalize(
                        project.project_name
                    )
                ]

            if not exact:
                return None, "Project not found."

            candidate_sets.append({
                project.project_id
                for project in exact
            })

        unit_identifiers = [
            intent.unit_id,
            intent.unit_name,
            intent.unit_number,
        ]

        if any(unit_identifiers):

            matched_units = []

            for unit in self.snapshot.units:

                values = [
                    unit.unit_id,
                    unit.unit_name,
                    unit.unit_code,
                ]

                if any(
                    normalize(identifier)
                    == normalize(value)
                    for identifier in unit_identifiers
                    if identifier
                    for value in values
                    if value
                ):
                    matched_units.append(unit)

            if not matched_units:
                return None, (
                    "I couldn't find that unit in your "
                    "authorized inventory."
                )

            candidate_sets.append({
                unit.project_id
                for unit in matched_units
                if unit.project_id
            })

        if not candidate_sets:
            return None, (
                "Please specify a project name, "
                "number, ID, or unit."
            )

        matching_ids = set.intersection(
            *candidate_sets
        )

        matches = [
            project
            for project in projects
            if project.project_id in matching_ids
        ]

        if len(matches) == 1:
            return matches[0], None

        if len(matches) > 1:
            return None, (
                "Multiple projects match your request. "
                "Please specify the exact project."
            )

        return None, (
            "No project matches the supplied identifiers."
        )

    @staticmethod
    def project_summary(project):

        return {
            "project_name": project.project_name,
            "project_id": project.project_id,
            "project_number": project.project_number,
            "location": project.location,
            "starting_price_aed": (
                project.starting_price
            ),
            "total_units": project.total_units,
            "bedrooms": (
                project.bedrooms_categories
            ),
            "apartments": project.apartments,
            "payment_plan": project.payment_plan,
            "construction_status": (
                project.construction_status
            ),
            "handover_date": project.handover_date,
            "completion_date": (
                project.completion_date
            ),
            "project_configuration": (
                project.project_configuration
            ),
            "service_charge": (
                project.service_charge
            ),
            "amenities": project.amenities,
            "places_nearby": (
                project.places_nearby
            ),
        }


    async def get_project_map_url(self, project):

        project_id = project.project_id

        if not project_id:
            return None

        try:

            # Step 1: Call new Project Coordinates API.
            coordinates = (
                await self.coordinates_connector
                .fetch_coordinates(
                    project_id=str(project_id),
                    access_token=self.access_token,
                )
            )

            if not coordinates:

                logger.info(
                    "PROJECT_COORDINATES_NOT_FOUND | "
                    "project_id=%s",
                    project_id,
                )

                return None

            latitude = coordinates.get(
                "latitude"
            )

            longitude = coordinates.get(
                "longitude"
            )

            if latitude is None or longitude is None:

                logger.info(
                    "PROJECT_COORDINATES_MISSING | "
                    "project_id=%s",
                    project_id,
                )

                return None

            # Step 2: Generate Google Maps URL.
            # The paid Google API key is used inside
            # generate_map_url_from_coordinates().
            secrets = await load_application_secrets()

            map_url = (
                await generate_map_url_from_coordinates(
                    latitude=latitude,
                    longitude=longitude,
                    google_api_key=secrets.google_maps_api_key.get_secret_value(),
                )
            )

            logger.info(
                "PROJECT_MAP_URL_GENERATED | "
                "project_id=%s",
                project_id,
            )

            return map_url

        except Exception:

            logger.exception(
                "PROJECT_MAP_GENERATION_FAILED | "
                "project_id=%s",
                project_id,
            )

            # Map failure should not prevent
            # project information from displaying.
            return None

    async def get_project_map_urls(self, projects):

        # Limit concurrent calls to external APIs.
        semaphore = asyncio.Semaphore(5)

        async def fetch_one(project):

            async with semaphore:

                map_url = await (
                    self.get_project_map_url(project)
                )

                return (
                    str(project.project_id),
                    map_url,
                )

        results = await asyncio.gather(
            *[
                fetch_one(project)
                for project in projects
            ]
        )

        return dict(results)



    def render_cards(
        self,
        projects,
        map_urls=None,
    ):
        cards = []

        map_urls = map_urls or {}

        for project in projects:

            # Direct project_id lookup.
            map_url = map_urls.get(
                str(project.project_id)
            )

            # Render the existing individual project card.
            html = self.templates.render(
                "project_information_card.html.j2",

                project_name=project.project_name,

                image_url=safe_image_url(
                    project.project_image
                ),

                starting_price=(
                    project.starting_price
                ),

                total_units=project.total_units,

                location=project.location,

                map_url=map_url,
            )

            # Collect HTML instead of creating
            # a separate SSE block for each project.
            cards.append(html)

        if not cards:
            return []

        # Combine all cards into one HTML container.
        combined_html = (
            '<div class="danube-project-cards">'
            + "\n".join(cards)
            + "</div>"
        )

        # Return exactly one HTML block.
        return [
            {
                "card_type": "project_information",
                "html": combined_html,
            }
        ]

    
    async def handle_project_amenities(
        self,
        intent,
        projects,
    ):
        """
        Fetch project-specific amenities from OSF Portfolio.

        Reuses the existing curl_cffi connector used
        by the project 3D tour functionality.

        Returns the original amenities HTML template
        populated with dynamic names and images.
        """

        # 1. Resolve requested project using existing logic.
        project, error = self.resolve_project(
            intent,
            projects,
        )

        if error:
            return self.failure(error)

        # 2. Fetch OSF Portfolio API using existing connector.
        try:
            portfolio = (
                await self.tour_connector.fetch_portfolio()
            )

        except Exception:
            logger.exception(
                "PROJECT_AMENITIES_API_FAILED | "
                "project_id=%s",
                project.project_id,
            )

            return self.failure(
                "Project amenities are temporarily "
                "unavailable. Please try again."
            )

        # 3. Normalize official project name.
        project_key = normalize(
            normalize_map_project_name(
                project.project_name
            )
        )

        # 4. Find matching OSF Portfolio project.
        matching_projects = []

        for item in portfolio:

            if not isinstance(item, dict):
                continue

            portfolio_name = (
                item.get("title")
                or item.get("name")
                or ""
            )

            portfolio_key = normalize(
                normalize_map_project_name(
                    portfolio_name
                )
            )

            if portfolio_key == project_key:
                matching_projects.append(item)

        if not matching_projects:

            logger.info(
                "PROJECT_AMENITIES_PROJECT_NOT_FOUND | "
                "project_name=%s",
                project.project_name,
            )

            return self.failure(
                f"No amenities were found for "
                f"{project.project_name}."
            )

        # 5. Extract amenity names and image URLs.
        amenities = []
        seen = set()

        for item in matching_projects:

            meta = item.get("meta") or {}

            if not isinstance(meta, dict):
                continue

            # IMPORTANT:
            # The OSF API uses the key "aminities".
            raw_amenities = meta.get("aminities") or []

            if not isinstance(raw_amenities, list):
                continue

            for amenity in raw_amenities:

                if not isinstance(amenity, dict):
                    continue

                label = str(
                    amenity.get("label") or ""
                ).strip()

                image_url = safe_amenity_image_url(
                    amenity.get("category_image")
                )

                if not label or not image_url:
                    continue

                # Avoid duplicate cards.
                unique_key = (
                    label.casefold(),
                    image_url,
                )

                if unique_key in seen:
                    continue

                seen.add(unique_key)

                amenities.append({
                    "label": label,
                    "category_image": image_url,
                })

        # 6. No usable amenities.
        if not amenities:

            logger.info(
                "PROJECT_AMENITIES_EMPTY | "
                "project_name=%s",
                project.project_name,
            )

            return self.failure(
                f"No amenities are currently available "
                f"for {project.project_name}."
            )

        # 7. Render original amenities HTML.
        html = self.templates.render(
            "amenities.html.j2",
            amenities=amenities,
        )

        logger.info(
            "PROJECT_AMENITIES_RENDERED | "
            "project_name=%s | count=%s",
            project.project_name,
            len(amenities),
        )

        # 8. Return standard HandlerResult.
        return HandlerResult(
            intent="project_information",

            html_blocks=[
                {
                    "card_type": "amenities",
                    "html": html,
                }
            ],

            files=[],

            messages=[],

            generation_context={
                "service": "project_information",
                "operation": "amenities",
                "result_count": 1,
                "project_name": project.project_name,
                "amenities_count": len(amenities),
                "projects": [
                    {
                        "project_name": project.project_name,
                        "amenities": [
                            item["label"]
                            for item in amenities
                        ],
                    }
                ],
            },

            has_data=True,
        )


    async def get_construction_update_url(
        self,
        project_name: str,
    ) -> str | None:

        # 1. Reuse existing OSF Portfolio connector.
        portfolio = await self.tour_connector.fetch_portfolio()

        # 2. Normalize project name.
        project_key = normalize(
            normalize_map_project_name(project_name)
        )

        # 3. Match OSF title with project name.
        matches = []

        for item in portfolio:

            if not isinstance(item, dict):
                continue

            osf_name = (
                item.get("title")
                or item.get("name")
                or ""
            )

            osf_key = normalize(
                normalize_map_project_name(osf_name)
            )

            if osf_key == project_key:
                matches.append(item)

        # Avoid incorrect project ID selection.
        if len(matches) != 1:
            logger.warning(
                "CONSTRUCTION_OSF_MATCH_FAILED | "
                "project=%s | matches=%s",
                project_name,
                len(matches),
            )
            return None

        # 4. Retrieve OSF project ID.
        osf_project_id = matches[0].get("id")

        if (
            osf_project_id is None
            or not str(osf_project_id).isdigit()
        ):
            return None

        # 5. Call Construction Update API.
        construction_url = (
            await self.construction_connector
            .fetch_construction_url(
                osf_project_id=str(osf_project_id)
            )
        )

        return construction_url


    async def get_nearby_places(
        self,
        project_name: str,
    ) -> list[dict]:
        """
        Fetch nearby places from OSF Portfolio API
        for the specified project.

        Returns:
        [
            {"title": "...", "image": "..."}
        ]
        """

        portfolio = (
            await self.tour_connector.fetch_portfolio()
        )

        project_key = normalize(
            normalize_map_project_name(project_name)
        )

        matching_projects = []

        for item in portfolio:

            if not isinstance(item, dict):
                continue

            osf_name = (
                item.get("title")
                or item.get("name")
                or ""
            )

            osf_key = normalize(
                normalize_map_project_name(osf_name)
            )

            if osf_key == project_key:
                matching_projects.append(item)

        if len(matching_projects) != 1:

            logger.warning(
                "NEARBY_PROJECT_MATCH_FAILED | "
                "project=%s | matches=%s",
                project_name,
                len(matching_projects),
            )

            return []

        meta = (
            matching_projects[0].get("meta") or {}
        )

        if not isinstance(meta, dict):
            return []

        raw_places = meta.get(
            "danube_why_near_location_content"
        ) or []

        if not isinstance(raw_places, list):
            return []

        nearby_places = []
        seen = set()

        for item in raw_places:

            if not isinstance(item, dict):
                continue

            title = str(
                item.get(
                    "danube_why_near_location_title"
                ) or ""
            ).strip()

            image = safe_amenity_image_url(
                item.get(
                    "danube_why_near_location_image"
                )
            )

            if not title or not image:
                continue

            unique_key = (
                title.casefold(),
                image,
            )

            if unique_key in seen:
                continue

            seen.add(unique_key)

            nearby_places.append({
                "title": title,
                "image": image,
            })

        logger.info(
            "NEARBY_PLACES_FETCHED | "
            "project=%s | count=%s",
            project_name,
            len(nearby_places),
        )

        return nearby_places

    
    async def handle_project_fields(
        self,
        intent,
        projects,
    ):
        """
        Preserve existing project field response text.

        For construction_status only, replace the
        HTML with the construction update link card.
        """

        # 1. Existing project resolution.
        project, error = self.resolve_project(
            intent,
            projects,
        )

        if error:
            return self.failure(error)

        # 2. Existing field extraction.
        fields = expand_fields(
            getattr(intent, "project_fields", None)
        )

        rows = field_rows(
            project,
            fields,
        )

        # 3. KEEP EXISTING RESPONSE UNCHANGED.
        answer = build_field_answer(
            project.project_name,
            rows,
        )

        # 4. Default existing HTML.
        html = self.templates.render(
            "project_fields.html.j2",
            project_name=project.project_name,
            rows=rows,
        )

        card_type = "project_fields"

        # 5. Change HTML only for a single
        # construction_status field request.
        if fields == ["construction_status"]:

            try:
                construction_url = (
                    await self.get_construction_update_url(
                        project.project_name
                    )
                )

                if construction_url:

                    html = self.templates.render(
                        "construction_update.html.j2",
                        project_name=project.project_name,
                        construction_update_url=construction_url,
                    )

                    card_type = "construction_update"

                    logger.info(
                        "CONSTRUCTION_HTML_RENDERED | "
                        "project=%s",
                        project.project_name,
                    )

                else:
                    logger.info(
                        "CONSTRUCTION_URL_NOT_AVAILABLE | "
                        "project=%s",
                        project.project_name,
                    )

            except Exception:
                logger.exception(
                    "CONSTRUCTION_HTML_FAILED | "
                    "project=%s",
                    project.project_name,
                )


        # 6. Nearby places HTML from OSF Portfolio.

        if fields == ["places_nearby"]:

            try:
                nearby_places = (
                    await self.get_nearby_places(
                        project.project_name
                    )
                )

                if nearby_places:

                    html = self.templates.render(
                        "nearbyplaces.html.j2",
                        nearby_places=nearby_places,
                    )

                    card_type = "nearby_places"

                    answer = (
                        f"Here are the places nearby "
                        f"{project.project_name}."
                    )

                    logger.info(
                        "NEARBY_HTML_RENDERED | "
                        "project=%s | count=%s",
                        project.project_name,
                        len(nearby_places),
                    )

                else:
                    logger.info(
                        "NEARBY_PLACES_NOT_AVAILABLE | "
                        "project=%s",
                        project.project_name,
                    )

            except Exception:

                logger.exception(
                    "NEARBY_PLACES_FAILED | "
                    "project=%s",
                    project.project_name,
                )

        # 7. Existing response structure.
        return HandlerResult(
            intent="project_information",

            html_blocks=[
                {
                    "card_type": card_type,
                    "html": html,
                }
            ],

            files=[],

            # SAME existing response.
            messages=[answer],

            generation_context={
                "service": "project_information",
                "operation": "field",
                "result_count": 1,
                "project_name": project.project_name,
                "fields": fields,
                "projects": [
                    self.project_summary(project)
                ],
            },

            has_data=True,
        )

    async def handle_project_faqs(
        self,
        intent,
        projects,
    ):
        """
        Show all FAQs of one project from OSF Portfolio.

        Reuses the existing OSF connector and the same
        project resolution / name matching as amenities.
        FAQ answers are converted to safe text blocks
        before rendering (see app.utils.project_faqs).
        """

        # 1. Resolve requested project using existing logic.
        project, error = self.resolve_project(
            intent,
            projects,
        )

        if error:
            return self.failure(error)

        # 2. Fetch OSF Portfolio API using existing connector.
        try:
            portfolio = (
                await self.tour_connector.fetch_portfolio()
            )

        except Exception:
            logger.exception(
                "PROJECT_FAQS_API_FAILED | "
                "project_id=%s",
                project.project_id,
            )

            return self.failure(
                "Project FAQs are temporarily "
                "unavailable. Please try again."
            )

        # 3. Find matching OSF Portfolio project
        # (same matching as amenities).
        project_key = normalize(
            normalize_map_project_name(
                project.project_name
            )
        )

        matching_projects = [
            item
            for item in portfolio or []
            if isinstance(item, dict)
            and normalize(
                normalize_map_project_name(
                    item.get("title")
                    or item.get("name")
                    or ""
                )
            ) == project_key
        ]

        # 4. Extract FAQs.
        faqs = extract_project_faqs(
            matching_projects
        )

        if not faqs:

            logger.info(
                "PROJECT_FAQS_EMPTY | "
                "project_name=%s | osf_matches=%s",
                project.project_name,
                len(matching_projects),
            )

            return self.failure(
                f"No FAQs are currently available "
                f"for {project.project_name}."
            )

        # 5. Render FAQ card.
        html = self.templates.render(
            "project_faqs.html.j2",
            project_name=project.project_name,
            faqs=faqs,
        )

        logger.info(
            "PROJECT_FAQS_RENDERED | "
            "project_name=%s | count=%s",
            project.project_name,
            len(faqs),
        )

        # 6. Return standard HandlerResult. Only the
        # questions go to the LLM; answers stay in the card.
        return HandlerResult(
            intent="project_information",

            html_blocks=[
                {
                    "card_type": "project_faqs",
                    "html": html,
                }
            ],

            files=[],

            messages=[],

            generation_context={
                "service": "project_information",
                "operation": "faq",
                "result_count": 1,
                "project_name": project.project_name,
                "faq_count": len(faqs),
                "projects": [
                    {
                        "project_name": project.project_name,
                        "faq_questions": [
                            faq["question"]
                            for faq in faqs
                        ],
                    }
                ],
            },

            has_data=True,
        )

    async def handle_project_tour(
        self,
        intent,
        projects,
    ):

        """
        Fetch and render the 3D tour of a project.

        OSF Portfolio API is retained for this.
        """

        project, error = self.resolve_project(
            intent,
            projects,
        )

        if error:
            return self.failure(error)

        # Fetch OSF Portfolio API.
        try:

            portfolio = (
                await self.tour_connector
                .fetch_portfolio()
            )

        except Exception:

            logger.exception(
                "PROJECT_TOUR_API_FAILED"
            )

            return self.failure(
                "The project tour is temporarily "
                "unavailable. Please try again."
            )

        # Build existing video lookup.
        tour_lookup = (
            build_project_tour_lookup(
                portfolio
            )
        )

        # Keep existing tour-name matching.
        project_key = (
            normalize_map_project_name(
                project.project_name
            )
        )

        video_url = tour_lookup.get(
            project_key
        )

        if not video_url:

            logger.info(
                "PROJECT_TOUR_NOT_FOUND | "
                "project_id=%s",
                project.project_id,
            )

            return self.failure(
                f"A 3D tour is not currently "
                f"available for "
                f"{project.project_name}."
            )

        html = self.templates.render(
            "virtual_tour_file.html.j2",
            tour_url=video_url,
        )

        logger.info(
            "PROJECT_TOUR_FOUND | "
            "project_id=%s",
            project.project_id,
        )

        return HandlerResult(
            intent="project_information",

            html_blocks=[
                {
                    "card_type": "project_tour",
                    "html": html,
                }
            ],

            files=[],

            messages=[],

            generation_context={
                "service": (
                    "project_information"
                ),
                "operation": "tour",
                "result_count": 1,
                "project_name": (
                    project.project_name
                ),
                "tour_available": True,
                "projects": [
                    self.project_summary(
                        project
                    )
                ],
            },

            has_data=True,
        )

    @staticmethod
    def display_value(value):

        """Convert API values to display text safely."""

        if value is None or value == "":
            return None

        if isinstance(value, dict):
            return None

        if isinstance(
            value,
            (list, tuple, set),
        ):

            values = [
                str(item).strip()
                for item in value
                if isinstance(
                    item,
                    (str, int, float),
                )
                and str(item).strip()
            ]

            return (
                ", ".join(values)
                if values
                else None
            )

        return str(value).strip() or None

    def render_project_details(
        self,
        project,
        map_url=None,
    ):

        """Render one Figma-style project details card."""

        html = self.templates.render(
            "project_details.html.j2",

            project_name=project.project_name,

            map_url=map_url,

            location=self.display_value(
                project.location
            ),

            project_configuration=(
                self.display_value(
                    project.project_configuration
                )
            ),

            bedrooms=self.display_value(
                project.bedrooms_categories
            ),

            total_units=project.total_units,

            amenities=self.display_value(
                project.amenities
            ),

            completion_date=self.display_value(
                project.completion_date
            ),

            starting_price=self.display_value(
                project.starting_price
            ),

            payment_plan=self.display_value(
                project.payment_plan
            ),

            construction_status=self.display_value(
                project.construction_status
            ),

            handover_date=self.display_value(
                project.handover_date
            ),

            description=None,

            details_url=None,

            available_units_url=None,
        )

        return [{
            "card_type": "project_details",
            "html": html,
        }]


    async def handle(self, intent):

        try:

            # Step 1: Fetch authorized project data.
            projects = (
                await self.connector.fetch_projects(
                    inventory_token=(
                        self.inventory_token
                    ),
                    access_token=(
                        self.access_token
                    ),
                )
            )

            projects = [
                project
                for project in projects
                if (
                    project.project_id
                    and project.project_name
                )
            ]

            operation = (
                intent.project_operation
                or "details"
            )

            if operation == "amenities":

                return await self.handle_project_amenities(
                    intent,
                    projects,
                )

            # Project FAQs use OSF Portfolio API.
            if operation == "faq":

                return await self.handle_project_faqs(
                    intent,
                    projects,
                )

            # Specific project facts from the Projects API.
            # Without any recognised field, use the existing
            # full details card instead.
            if operation == "field":

                if expand_fields(
                    getattr(intent, "project_fields", None)
                ):
                    return await self.handle_project_fields(
                        intent,
                        projects,
                    )

                operation = "details"

            # Step 2: 3D tour uses OSF Portfolio API.
            if operation == "tour":

                return await (
                    self.handle_project_tour(
                        intent,
                        projects,
                    )
                )

            # Step 3: Select projects.
            elif operation == "latest":

                limit = min(
                    max(
                        intent.project_limit or 3,
                        1,
                    ),
                    20,
                )

                selected = projects[:limit]

            elif operation == "list":

                limit = min(
                    max(
                        intent.project_limit or 5,
                        1,
                    ),
                    20,
                )

                selected = projects[:limit]

            elif operation == "location_search":

                location = normalize(
                    intent.project_location
                )

                if not location:

                    return self.failure(
                        "Which location would "
                        "you like to search?"
                    )

                selected = [
                    project
                    for project in projects
                    if location in normalize(
                        project.location
                    )
                ][:20]

            else:

                project, error = (
                    self.resolve_project(
                        intent,
                        projects,
                    )
                )

                if error:
                    return self.failure(error)

                selected = [project]

            if not selected:

                return self.failure(
                    "No matching Danube "
                    "projects were found."
                )

            # Step 4: Prepare project summaries.
            summaries = [
                self.project_summary(
                    project
                )
                for project in selected
            ]

            # Step 5: Generate map URLs only for
            # operations that render project list cards.
            map_urls = (
                await self.get_project_map_urls(
                    selected
                )
            )

            # Step 6: Return existing HandlerResult.
            return HandlerResult(
                intent="project_information",

                html_blocks=(
                    self.render_project_details(
                        selected[0],
                        map_url=map_urls.get(
                            str(selected[0].project_id)
                        ),
                    )
                    if operation == "details"
                    else self.render_cards(
                        selected,
                        map_urls=map_urls,
                    )
                ),

                files=[],

                messages=[],

                generation_context={
                    "service": (
                        "project_information"
                    ),

                    "operation": operation,

                    "result_count": len(selected),

                    "requested_location": (
                        intent.project_location
                    ),

                    "projects": summaries,
                },

                has_data=True,
            )

        except ProjectInformationAPIError:

            logger.exception(
                "PROJECT_INFORMATION_FETCH_FAILED"
            )

            return self.failure(
                "Project information is temporarily "
                "unavailable. Please try again."
            )
