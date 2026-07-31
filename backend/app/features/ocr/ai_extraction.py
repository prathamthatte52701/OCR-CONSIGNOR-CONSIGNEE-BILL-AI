"""Jinja2 prompt rendering + Groq call for Part 1 header and Part 2 table extraction."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from app.features.ocr.json_parsing import parse_json_object
from app.features.ocr.providers.base import AIProvider
from app.features.ocr.providers.groq_provider import GroqProvider

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

SYSTEM_PROMPT = (
    "You are a precise document data extraction engine. You always respond with a single "
    "valid JSON object and nothing else. You never guess a value you are not confident about "
    "- you return null instead."
)

_provider: AIProvider | None = None


def get_provider() -> AIProvider:
    global _provider
    if _provider is None:
        _provider = GroqProvider()
    return _provider


async def extract_part1_header(
    consignee_column_text: str, consignor_column_text: str
) -> dict[str, Any]:
    template = _env.get_template("delivery_challan_header.j2")
    user_prompt = template.render(
        consignee_column_text=consignee_column_text,
        consignor_column_text=consignor_column_text,
    )
    raw_response = await get_provider().extract(SYSTEM_PROMPT, user_prompt)
    return parse_json_object(raw_response)


async def extract_part2_summary(summary_text: str) -> dict[str, Any]:
    template = _env.get_template("uncoded_rgp_table.j2")
    user_prompt = template.render(summary_text=summary_text)
    raw_response = await get_provider().extract(SYSTEM_PROMPT, user_prompt)
    return parse_json_object(raw_response)
