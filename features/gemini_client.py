import os
from google import genai
from google.genai import types


def generate_text(prompt, max_output_tokens=None, temperature=None):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=api_key)

    config = None

    if max_output_tokens is not None or temperature is not None:
        config = types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            temperature=temperature
        )

    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        contents=prompt,
        config=config
    )

    return response.text or ""
