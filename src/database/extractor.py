"""Generic LLM extraction: raw text -> validated Pydantic/SQLModel object.

Schema-agnostic by design: `LLMExtractor.extract(text, schema_cls)` works
with ANY Pydantic (or SQLModel) class. The prompt is built from the
class' JSON schema, so adding/removing fields in the schema class is the
ONLY change ever needed — this file never changes.

The LLM call goes through a tiny OpenAI-compatible chat client (stdlib
urllib, no new dependency). Point it at any server that speaks
`/v1/chat/completions` (LM Studio, OpenAI, vLLM, Ollama, ...) via env:

    PME_LLM_BASE_URL   default http://localhost:1234/v1
    PME_LLM_MODEL      default qwen/qwen3.8-27b
    PME_LLM_API_KEY    optional (LM Studio needs none)
    PME_LLM_MAX_TOKENS default 8192 (reasoning models burn budget thinking)
    PME_LLM_TIMEOUT    default 300 seconds

In tests (or anywhere) pass any object with `complete(prompt) -> str`.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "qwen/qwen3.8-27b"


class ExtractionError(RuntimeError):
    """The LLM output could not be turned into a valid schema instance."""


def first_json_object(raw: str) -> str | None:
    """First balanced top-level ``{...}`` in ``raw`` (string-aware).

    Lets JSON embedded in prose or ```-fenced model output still parse.
    """
    start = raw.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(raw)):
            ch = raw[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return raw[start : i + 1]
        start = raw.find("{", start + 1)
    return None


def build_prompt(schema_cls: type[BaseModel], text: str) -> str:
    """Whole LLM contract in one place: the class' JSON schema + rules + text.

    Pure function — unit-testable without a model. Because the schema block
    comes from ``schema_cls.model_json_schema()``, any field added to or
    removed from the class shows up in the prompt automatically.
    """
    schema = json.dumps(schema_cls.model_json_schema(), indent=2)
    return (
        "You are transcribing a medical examination report into structured data.\n"
        "Fill in the JSON object from the report text below.\n"
        "RULES:\n"
        "1. Output ONLY one JSON object. No markdown, no commentary.\n"
        "2. Use exactly the property names shown in the schema.\n"
        "3. Any field that is not present in the text must be null. Never guess.\n"
        "4. All dates must be YYYY-MM-DD.\n"
        "5. Array fields: one object per printed row, in printed order.\n\n"
        "JSON SCHEMA:\n"
        f"{schema}\n\n"
        "REPORT TEXT:\n"
        f"{text}\n\n"
        "JSON OBJECT:"
    )


class OpenAICompatClient:
    """Minimal OpenAI-compatible chat client, stdlib only.

    Only needs ``complete(prompt) -> str``; that is the entire interface
    ``LLMExtractor`` relies on, so any other backend can be swapped in.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ):
        self.base_url = (
            base_url or os.getenv("PME_LLM_BASE_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        self.model = model or os.getenv("PME_LLM_MODEL", DEFAULT_MODEL)
        self.api_key = (
            api_key if api_key is not None else os.getenv("PME_LLM_API_KEY", "")
        )
        self.max_tokens = int(max_tokens or os.getenv("PME_LLM_MAX_TOKENS", "8192"))
        self.timeout = float(timeout or os.getenv("PME_LLM_TIMEOUT", "300"))

    def complete(self, prompt: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except urllib.error.URLError as exc:
            raise ExtractionError(
                f"LLM server unreachable at {self.base_url}: {exc}"
            ) from exc
        try:
            return payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ExtractionError(
                f"Unexpected LLM response shape: {str(payload)[:200]}"
            ) from exc


class LLMExtractor:
    """Generic extractor: (raw text, any Pydantic schema class) -> instance.

    ``extract`` is the whole pipeline step — prompt, LLM call, tolerant
    JSON recovery, and validation against ``schema_cls``. Nothing here
    depends on a particular schema, so schema edits never touch this file.
    """

    def __init__(self, client: OpenAICompatClient | None = None):
        self.client = client or OpenAICompatClient()

    def extract(self, text: str, schema_cls: type[T]) -> T:
        if not text or not text.strip():
            raise ExtractionError("input text is empty")

        raw = self.client.complete(build_prompt(schema_cls, text))

        candidate = first_json_object(raw)
        if candidate is None:
            raise ExtractionError(
                f"no JSON object in LLM output: {raw[:200]!r}"
            )
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"LLM output is not valid JSON: {exc}") from exc

        # Primary keys are server-assigned; never let the LLM choose one.
        if "id" in data and "id" in schema_cls.model_fields:
            data.pop("id")

        try:
            return schema_cls.model_validate(data)
        except ValidationError as exc:
            raise ExtractionError(
                f"{schema_cls.__name__} validation failed: {exc.errors()[:5]}"
            ) from exc
