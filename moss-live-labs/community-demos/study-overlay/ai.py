from __future__ import annotations

import requests

from settings import load_settings


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "~x-ai/grok-latest"


class AIError(RuntimeError):
    pass


BASE_TUTOR_PROMPT = """You are StudyOverlay, an expert AI study tutor looking at the user's current screen.
Identify the visible question, content, concept, formula, graph, code, or notes.
Explain it clearly like a tutor: give the relevant background, the reasoning steps, and the answer when appropriate.
If the screen is ambiguous, state what you can infer and ask the user to capture again with more of the material visible.
Use Markdown. For math, use KaTeX-compatible delimiters: $...$ for inline math and $$...$$ for display math.
Keep the answer concise enough to fit in a desktop overlay, but do not give a terse answer without teaching the concept."""


def _api_key() -> str:
    key = load_settings().get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise AIError("Missing OPENROUTER_API_KEY. Open settings and add your OpenRouter key.")
    return key


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://studyoverlay.local",
        "X-OpenRouter-Title": "StudyOverlay",
    }


def _post_chat(messages: list[dict], *, max_tokens: int = 900, temperature: float = 0.25) -> str:
    payload = {
        "model": DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        response = requests.post(OPENROUTER_URL, headers=_headers(), json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise AIError(f"OpenRouter request failed: {exc}") from exc
    except ValueError as exc:
        raise AIError("OpenRouter returned a non-JSON response.") from exc

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError(f"OpenRouter response did not contain a chat message: {data}") from exc


def explain_screenshot(image_data_url: str, related_context: str = "", user_prompt: str = "") -> str:
    context_block = ""
    if related_context.strip():
        context_block = (
            "\n\nRelated context from earlier in this session:\n"
            f"{related_context.strip()}\n"
            "Only connect it to the current screen when it is genuinely relevant."
        )

    prompt_text = "Please explain the study material visible in this screenshot."
    if user_prompt.strip():
        prompt_text = (
            "Please use the screenshot and this extra instruction from the user:\n\n"
            f"{user_prompt.strip()}"
        )

    messages = [
        {"role": "system", "content": BASE_TUTOR_PROMPT + context_block},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt_text,
                },
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_url},
                },
            ],
        },
    ]
    return _post_chat(messages)
