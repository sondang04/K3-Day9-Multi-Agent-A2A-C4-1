"""
LLM Client for Multi-Agent E-commerce Dispute Resolution
Uses OpenRouter API with OpenAI-compatible SDK
"""

import os
from typing import Optional
from openai import OpenAI
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, MODEL_NAME


class LLMClient:
    """OpenRouter LLM client using OpenAI SDK"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048
    ):
        self.api_key = api_key or OPENROUTER_API_KEY
        self.base_url = base_url or OPENROUTER_BASE_URL
        self.model = model or MODEL_NAME
        self.temperature = temperature
        self.max_tokens = max_tokens

        if not self.api_key:
            raise ValueError("OpenRouter API key is required. Set OPENROUTER_API_KEY in .env")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def chat(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max_tokens

        Returns:
            Response content as string
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens
        )
        return response.choices[0].message.content

    def chat_with_json(
        self,
        messages: list[dict],
        temperature: float = 0.0
    ) -> dict:
        """
        Send a chat request expecting JSON response.
        Returns parsed JSON dict.
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"}
        )
        import json
        return json.loads(response.choices[0].message.content)


# Default client instance
default_client = LLMClient()


def get_client() -> LLMClient:
    """Get the default LLM client"""
    return default_client
