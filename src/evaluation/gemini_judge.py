"""Gemini-backed DeepEval judge (ref-doc.md §4 Evaluation: LLM-as-judge = Gemini).

DeepEval's built-in metrics default to an OpenAI judge model and can prompt
for a Confident AI cloud login. This module supplies a DeepEvalBaseLLM
subclass backed by the same Gemini factory and retry/backoff wrapper the
rest of the app uses (src/llm.py), so evaluation never touches OpenAI or any
other provider (§3.4 Gemini-Only Rule) and inherits the same NFR-04
resilience the live graph already relies on.

Checked against the installed deepeval==4.2.3's abstract base
(deepeval/models/base_model.py): a subclass must implement load_model,
generate, a_generate and get_model_name. Metrics call generate_with_schema /
a_generate_with_schema (defined on the base class), which pass a `schema`
kwarg through to generate/a_generate and, when the return value is an
instance of that schema, use it directly -- so we return the parsed pydantic
object straight from Gemini's structured output instead of a JSON string,
skipping DeepEval's own JSON-repair path entirely.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional, Type, TypeVar

from deepeval.models.base_model import DeepEvalBaseLLM
from pydantic import BaseModel

from src.agents._common import extract_text
from src.config import settings
from src.llm import ainvoke_with_backoff, get_llm

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class GeminiJudge(DeepEvalBaseLLM):
    """DeepEval judge model backed by Gemini (role='judge' in src.llm.get_llm)."""

    def __init__(self, *, temperature: float = 0.0) -> None:
        self._temperature = temperature
        super().__init__(model=settings.gemini_judge_model)

    def load_model(self, *args: Any, **kwargs: Any) -> Any:
        return get_llm(role="judge", temperature=self._temperature)

    def get_model_name(self, *args: Any, **kwargs: Any) -> str:
        return self.name or settings.gemini_judge_model

    async def a_generate(
        self, prompt: str, schema: Optional[Type[SchemaT]] = None, *args: Any, **kwargs: Any
    ) -> Any:
        llm = self.model.with_structured_output(schema) if schema is not None else self.model
        result = await ainvoke_with_backoff(llm, prompt)
        return result if schema is not None else extract_text(result.content)

    def generate(
        self, prompt: str, schema: Optional[Type[SchemaT]] = None, *args: Any, **kwargs: Any
    ) -> Any:
        # DeepEval's sync path; used outside an already-running event loop only
        # (the eval harness itself runs everything through a_generate).
        return asyncio.run(self.a_generate(prompt, schema=schema))
