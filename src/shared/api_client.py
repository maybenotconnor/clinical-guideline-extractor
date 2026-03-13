"""Unified API clients for Claude and Gemini with retry logic."""

import base64
import os
import time
from pathlib import Path

import anthropic
from google import genai
from google.genai import types as genai_types
from rich.console import Console

from .cost_tracker import CostTracker

console = Console()

# Models
CLAUDE_SONNET = "claude-sonnet-4-20250514"
GEMINI_FLASH = "gemini-3-flash-preview"
GEMINI_PRO = "gemini-3.1-pro-preview"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0


def _retry(func, retries=MAX_RETRIES, base_delay=RETRY_BASE_DELAY):
    """Retry with exponential backoff."""
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            if attempt == retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            console.print(f"  [yellow]Retry {attempt + 1}/{retries} after {delay}s: {e}[/yellow]")
            time.sleep(delay)


class ClaudeClient:
    def __init__(self, cost_tracker: CostTracker | None = None):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.cost_tracker = cost_tracker

    def extract_page(
        self,
        image_path: Path,
        prompt: str,
        stage: str = "extraction",
        page: int | None = None,
        model: str = CLAUDE_SONNET,
    ) -> str:
        """Send a page image + prompt to Claude, return text response."""
        image_data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")
        media_type = "image/png"

        def _call():
            response = self.client.messages.create(
                model=model,
                max_tokens=8192,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }],
            )
            if self.cost_tracker:
                self.cost_tracker.record(
                    model=model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    stage=stage,
                    page=page,
                )
            return response.content[0].text

        return _retry(_call)

    def verify_page(
        self,
        image_path: Path,
        extraction_text: str,
        verify_prompt: str,
        stage: str = "validation",
        page: int | None = None,
    ) -> str:
        """Send page image + extraction + verify prompt for error detection."""
        image_data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")

        def _call():
            response = self.client.messages.create(
                model=CLAUDE_SONNET,
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": f"{verify_prompt}\n\n---\n\nExtraction to verify:\n\n{extraction_text}",
                        },
                    ],
                }],
            )
            if self.cost_tracker:
                self.cost_tracker.record(
                    model=CLAUDE_SONNET,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    stage=stage,
                    page=page,
                )
            return response.content[0].text

        return _retry(_call)


class GeminiClient:
    def __init__(self, cost_tracker: CostTracker | None = None):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=api_key)
        self.cost_tracker = cost_tracker

    def extract_page(
        self,
        image_path: Path,
        prompt: str,
        stage: str = "extraction",
        page: int | None = None,
        model: str = GEMINI_FLASH,
    ) -> str | None:
        """Send a page image + prompt to Gemini. Returns None if safety-blocked."""
        image_data = image_path.read_bytes()

        def _call():
            response = self.client.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    genai_types.Part.from_bytes(data=image_data, mime_type="image/png"),
                ],
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                ),
            )

            # Check for safety filter block — response.text raises ValueError
            # when blocked, and candidates may be empty
            try:
                text = response.text
            except (ValueError, AttributeError):
                return None
            if not text:
                return None

            if self.cost_tracker and response.usage_metadata:
                self.cost_tracker.record(
                    model=model,
                    input_tokens=response.usage_metadata.prompt_token_count or 0,
                    output_tokens=response.usage_metadata.candidates_token_count or 0,
                    stage=stage,
                    page=page,
                )
            return text

        return _retry(_call)

    def tiebreak(
        self,
        image_path: Path,
        prompt: str,
        stage: str = "tiebreak",
        page: int | None = None,
    ) -> str | None:
        """Send tiebreak request to Gemini Pro."""
        return self.extract_page(
            image_path=image_path,
            prompt=prompt,
            stage=stage,
            page=page,
            model=GEMINI_PRO,
        )
