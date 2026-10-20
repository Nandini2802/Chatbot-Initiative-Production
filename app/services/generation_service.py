import json
import logging
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.schemas.generation import GenerationResult


logger = logging.getLogger(__name__)

PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "prompts"
    / "generation_marketing_v1.md"
)


class GenerationService:

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
    ):
        self.client = client
        self.model = model

        self.system_prompt = PROMPT_PATH.read_text(
            encoding="utf-8"
        )

    async def generate(
        self,
        message: str,
        language: str,
        intents: list[str],
        service_results: dict[str, Any],
        history: list[dict] | None = None,
    ) -> GenerationResult:

        payload = {
            "user_message": message,
            "detected_language": language,
            "detected_intents": intents,
            "verified_service_results": service_results,
            "recent_conversation": history or [],
        }

        try:
            result = await self.client.responses.parse(
                model=self.model,
                instructions=self.system_prompt,
                input=json.dumps(
                    payload,
                    ensure_ascii=False,
                    default=str,
                ),
                text_format=GenerationResult,
            )

            generated = result.output_parsed

            if generated is None:
                raise ValueError(
                    "Generation returned no parsed output"
                )

            if not generated.response.strip():
                raise ValueError(
                    "Generation returned empty response"
                )

            # Enforce a maximum of three chips.
            generated.followups = [
                chip.strip()
                for chip in generated.followups
                if chip and chip.strip()
            ][:3]

            logger.info(
                "GENERATION_COMPLETED | "
                "model=%s | language=%s | "
                "followups=%s",
                self.model,
                language,
                len(generated.followups),
            )

            return generated

        except Exception:
            logger.exception(
                "GENERATION_FAILED | model=%s",
                self.model,
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
