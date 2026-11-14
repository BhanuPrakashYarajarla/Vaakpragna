import os
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


def generate_text(prompt, max_output_tokens=None, temperature=None):
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing")

    try:
        client = genai.Client(api_key=api_key)

        config = None

        if max_output_tokens is not None or temperature is not None:
            config = types.GenerateContentConfig(
                max_output_tokens=max_output_tokens,
                temperature=temperature
            )

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config
        )

        if not response.text:
            raise RuntimeError("Gemini returned an empty response")

        return response.text.strip()

    except Exception:
        logger.exception("Gemini API request failed. Model: %s", model)
        raise
