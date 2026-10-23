
import json
import logging
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.schemas.generation import GenerationResult


logger = logging.getLogger(__name__)

PROMPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "prompts"
)

MARKETING_PROMPT_PATH = (
    PROMPTS_DIR / "generation_marketing_v1.md"
)

INVENTORY_PROMPT_PATH = (
    PROMPTS_DIR / "generation_inventory_v1.md"
)


class GenerationService:

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
    ):
        self.client = client
        self.model = model

        # Existing Marketing prompt
        self.marketing_prompt = (
            MARKETING_PROMPT_PATH.read_text(
                encoding="utf-8"
            )
        )

        # New Inventory prompt
        self.inventory_prompt = (
            INVENTORY_PROMPT_PATH.read_text(
                encoding="utf-8"
            )
        )

        # Preserve existing attribute for compatibility
        self.system_prompt = self.marketing_prompt

    def _select_prompt(
        self,
        intents: list[str],
        service_results: dict[str, Any],
    ) -> str:
        """
        Select response generation instructions
        based on verified service results and intents.
        """

        service = service_results.get("service")

        # 1. Inventory-only request
        if (
            service == "inventory"
            and set(intents) == {"inventory"}
        ):
            return self.inventory_prompt

        # 2. Marketing-only request
        if (
            service == "marketing"
            and set(intents) == {"marketing"}
        ):
            return self.marketing_prompt

        # 3. Multi-intent request
        if service == "multi_intent":

            results = service_results.get("results", [])

            service_types = {
                item.get("service")
                for item in results
                if isinstance(item, dict)
            }

            instructions = [
                (
                    "You are the Danube Properties "
                    "response generation assistant.\n"
                    "Generate one concise response using "
                    "only verified backend service results.\n"
                    "Handle each requested service separately.\n"
                    "Never invent project names, unit details, "
                    "prices, availability, files, or links.\n"
                    "Follow the detected language.\n"
                    "Return the structured GenerationResult "
                    "with response and followups.\n"
                )
            ]

            if "marketing" in service_types:
                instructions.append(
                    "\n## Marketing Instructions\n"
                    + self.marketing_prompt
                )

            if "inventory" in service_types:
                instructions.append(
                    "\n## Inventory Instructions\n"
                    + self.inventory_prompt
                )

            return "\n\n".join(instructions)

        # 4. Fallback for existing functionalities
        return self.system_prompt

    async def generate(
        self,
        message: str,
        language: str,
        intents: list[str],
        service_results: dict[str, Any],
        history: list[dict] | None = None,
    ) -> GenerationResult:

        # 1. Select prompt based on service
        selected_prompt = self._select_prompt(
            intents=intents,
            service_results=service_results,
        )

        # 2. Prepare LLM input
        payload = {
            "user_message": message,
            "detected_language": language,
            "detected_intents": intents,
            "verified_service_results": service_results,
            "recent_conversation": history or [],
        }

        try:
            # 3. Call Microsoft Foundry
            result = await self.client.responses.parse(
                model=self.model,
                instructions=selected_prompt,
                input=json.dumps(
                    payload,
                    ensure_ascii=False,
                    default=str,
                ),
                text_format=GenerationResult,
            )

            # 4. Extract structured response
            generated = result.output_parsed

            if generated is None:
                raise ValueError(
                    "Generation returned no parsed output"
                )

            if not generated.response.strip():
                raise ValueError(
                    "Generation returned empty response"
                )

            # 5. Clean and limit follow-up chips
            generated.followups = [
                chip.strip()
                for chip in generated.followups
                if isinstance(chip, str)
                and chip.strip()
            ][:3]

            # 6. Logging
            logger.info(
                "GENERATION_COMPLETED | "
                "model=%s | "
                "language=%s | "
                "intents=%s | "
                "service=%s | "
                "followups=%s",
                self.model,
                language,
                intents,
                service_results.get("service"),
                len(generated.followups),
            )

            return generated

        except Exception:
            logger.exception(
                "GENERATION_FAILED | "
                "model=%s | intents=%s",
                self.model,
                intents,
            )
            raise


def build_marketing_generation_context(
    project_name: str,
    requested_asset_types: list[str],
    files: list[dict],
    *,
    project_details: dict | None = None,
) -> dict:
    """
    Build a safe, compact marketing summary
    for LLM response generation.

    Files and project details must already have
    been validated by MarketingService.
    """

    asset_summary = []

    for file in files:
        asset_summary.append(
            {
                "name": file.get("name", ""),
                "type": file.get("type", ""),
                "format": file.get("format", ""),
            }
        )

    return {
        "service": "marketing",
        "project": project_name,
        "requested_asset_types": requested_asset_types,
        "assets_found": len(files) > 0,
        "asset_count": len(files),
        "available_assets": asset_summary,
        "verified_project_details": (
            project_details or {}
        ),
    }
