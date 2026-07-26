from __future__ import annotations
import asyncio
import json
from typing import (
    AsyncGenerator,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
)
from openai import APITimeoutError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel, ValidationError
from src.core.config import settings
from src.core.logging_settings import logger


T = TypeVar("T", bound=BaseModel)
RETRYABLE = (RateLimitError, APITimeoutError)


class LLMClient:
    def __init__(self) -> None:
        self._chat = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=settings.REQUEST_TIMEOUT_S,
        )
        embed_url = settings.OLLAMA_BASE_URL.rstrip("/")
        if not embed_url.endswith("/v1"):
            embed_url += "/v1"
        self._embed = AsyncOpenAI(
            api_key="sk-no-key-required",
            base_url=embed_url,
            timeout=settings.REQUEST_TIMEOUT_S,
        )
        self._embed_model: str = settings.OLLAMA_EMBED_MODEL

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        target = model or settings.LLM_MODEL_PRIMARY

        result, error = await self._try_with_retries(
            client=self._chat,
            model=target,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        if error is None:
            return result

        if target != settings.LLM_MODEL_CHEAP:
            logger.warning(
                "Primary model '{}' failed ({}), falling back to '{}'",
                target,
                type(error).__name__,
                settings.LLM_MODEL_CHEAP,
            )
            return await self._call(
                client=self._chat,
                model=settings.LLM_MODEL_CHEAP,
                messages=messages,
                temperature=temperature if temperature is not None else 0.1,
                max_tokens=max_tokens,
                **kwargs,
            )

        raise error

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        target = model or settings.LLM_MODEL_PRIMARY

        try:
            async for token in self._call_stream(
                client=self._chat,
                model=target,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            ):
                yield token
        except Exception as exc:
            logger.error("Streaming error on model '{}': {}", target, exc)
            yield f"\n\n[Ошибка: {exc}]"

    async def embed(self, text: str) -> List[float]:
        try:
            resp = await self._embed.embeddings.create(
                model=self._embed_model,
                input=text,
            )
            return resp.data[0].embedding
        except Exception as exc:
            logger.error("Embedding failed: {}", exc)
            return [0.0] * settings.EMBED_DIMENSION

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [await self.embed(t) for t in texts]

    @staticmethod
    async def _call(
        client: AsyncOpenAI,
        model: str,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        kwargs.pop("temperature", None)
        kwargs.pop("max_tokens", None)

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=(
                temperature
                if temperature is not None
                else settings.LLM_TEMPERATURE
            ),
            max_tokens=(
                max_tokens
                if max_tokens is not None
                else settings.LLM_MAX_TOKENS
            ),
            **kwargs,
        )
        return response.choices[0].message.content or ""

    @staticmethod
    async def _call_stream(
        client: AsyncOpenAI,
        model: str,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        kwargs.pop("temperature", None)
        kwargs.pop("max_tokens", None)

        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=(
                temperature
                if temperature is not None
                else settings.LLM_TEMPERATURE
            ),
            max_tokens=(
                max_tokens
                if max_tokens is not None
                else settings.LLM_MAX_TOKENS
            ),
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    @staticmethod
    async def _try_with_retries(
        client: AsyncOpenAI,
        model: str,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> tuple[str, Optional[Exception]]:
        last_exc: Optional[Exception] = None

        for attempt in range(settings.MAX_RETRIES):
            try:
                result = await LLMClient._call(
                    client=client,
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                return result, None
            except RETRYABLE as exc:
                last_exc = exc
                wait = min(2**attempt, 10)
                logger.warning(
                    "Retry {}/{} on {} for model '{}', sleep {}s",
                    attempt + 1,
                    settings.MAX_RETRIES,
                    type(exc).__name__,
                    model,
                    wait,
                )
                await asyncio.sleep(wait)

        return "", last_exc


async def parse_structured(
    llm: LLMClient,
    user_prompt: str,
    schema: Type[T],
    max_retries: int = 3,
    system_prompt: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
) -> T:
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)
    schema_instruction = (
        f"\n\nRespond strictly as JSON conforming to this schema:\n{schema_json}\n"
        f"No text before or after the JSON."
    )

    system_content = (
        (system_prompt + schema_instruction)
        if system_prompt
        else (
            f"Respond strictly as JSON conforming to the schema:\n{schema_json}\n"
            f"No text before or after the JSON."
        )
    )

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_prompt},
    ]

    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        raw = await llm.chat(
            messages, temperature=temperature, max_tokens=max_tokens
        )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            last_err = exc
            logger.warning(
                "parse_structured attempt {}/{}: invalid JSON: {}",
                attempt + 1,
                max_retries,
                exc,
            )
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": f"Invalid JSON: {exc}. Return a valid object that matches the schema.",
                }
            )
            continue

        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            last_err = exc
            logger.warning(
                "parse_structured attempt {}/{}: schema mismatch: {}",
                attempt + 1,
                max_retries,
                exc,
            )
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": f"JSON does not match the schema: {exc}. Fix it.",
                }
            )
            continue

    if last_err:
        raise last_err
    raise RuntimeError("Failed to parse structured output")