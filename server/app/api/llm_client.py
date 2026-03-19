"""
Unified LLM client supporting remote OpenAI-compatible APIs (DashScope/Qwen).

Usage:
    from api.llm_client import LLMClient

    client = LLMClient()
    response = client.chat("Summarize this lecture segment...")
    # or with full message control:
    response = client.chat_messages([
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is gradient descent?"},
    ])
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Generator

logger = logging.getLogger('polyu-video')

# Default configuration
DEFAULT_MODEL = "qwen2.5-7b-instruct"
DEFAULT_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class LLMClient:
    """
    Unified LLM client wrapping the OpenAI Python SDK for compatibility
    with DashScope and other OpenAI-compatible endpoints.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.api_base = api_base or os.environ.get("LLM_API_BASE", DEFAULT_API_BASE)
        self.temperature = temperature
        self.max_tokens = max_tokens

        if not self.api_key:
            logger.warning(
                "LLMClient initialized without API key. "
                "Set DASHSCOPE_API_KEY environment variable."
            )

        # Lazy import to avoid import errors if openai is not installed
        try:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
            )
            logger.info(
                f"LLMClient initialized: model={self.model}, "
                f"api_base={self.api_base}"
            )
        except ImportError:
            self._client = None
            logger.error(
                "openai package not installed. Install with: pip install openai"
            )

    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
    ) -> str:
        """
        Simple chat interface: send a single user prompt, get a string response.

        Args:
            prompt: User message text.
            system_prompt: Optional system message.
            temperature: Override default temperature.
            max_tokens: Override default max_tokens.
            response_format: If "json", request JSON output from the model.

        Returns:
            The assistant's response text.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return self.chat_messages(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    def chat_messages(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
    ) -> str:
        """
        Full chat interface with message list.

        Args:
            messages: List of {"role": "...", "content": "..."} dicts.
            temperature: Override default temperature.
            max_tokens: Override default max_tokens.
            response_format: If "json", request JSON output.

        Returns:
            The assistant's response text.

        Raises:
            RuntimeError: If client is not initialized or API call fails.
        """
        if not self._client:
            raise RuntimeError(
                "LLM client not initialized. Install openai package and set API key."
            )

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }

        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            logger.debug(
                f"LLM response: model={self.model}, "
                f"tokens={response.usage.total_tokens if response.usage else 'N/A'}"
            )
            return content or ""
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise RuntimeError(f"LLM API call failed: {e}") from e

    def stream_chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Generator[str, None, None]:
        """
        Streaming chat interface: yields tokens as they arrive.

        Args:
            prompt: User message text.
            system_prompt: Optional system message.
            temperature: Override default temperature.
            max_tokens: Override default max_tokens.

        Yields:
            Individual tokens/chunks from the model response.
        """
        if not self._client:
            raise RuntimeError(
                "LLM client not initialized. Install openai package and set API key."
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            stream = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"LLM streaming call failed: {e}")
            raise RuntimeError(f"LLM streaming call failed: {e}") from e

    def stream_chat_messages(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Generator[str, None, None]:
        """
        Streaming chat with full message list.

        Yields:
            Individual tokens/chunks from the model response.
        """
        if not self._client:
            raise RuntimeError(
                "LLM client not initialized. Install openai package and set API key."
            )

        try:
            stream = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"LLM streaming call failed: {e}")
            raise RuntimeError(f"LLM streaming call failed: {e}") from e

    def chat_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Chat expecting a JSON response. Parses the result automatically.

        Args:
            prompt: User message (should ask for JSON output).
            system_prompt: Optional system message.

        Returns:
            Parsed JSON dict from the model response.

        Raises:
            ValueError: If the response is not valid JSON.
        """
        response = self.chat(
            prompt=prompt,
            system_prompt=system_prompt,
            response_format="json",
            temperature=0.3,  # lower temperature for structured output
        )

        # Try to extract JSON from the response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to find JSON block in the response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            raise ValueError(
                f"LLM response is not valid JSON: {response[:500]}"
            )


# Module-level singleton for convenience
_default_client: Optional[LLMClient] = None


def get_llm_client(**kwargs) -> LLMClient:
    """
    Get the default LLM client singleton, or create one with custom settings.

    If called with no arguments, returns (or creates) a shared default client.
    If called with arguments, always creates a new client.
    """
    global _default_client
    if kwargs:
        return LLMClient(**kwargs)
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
