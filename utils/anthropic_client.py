"""Anthropic API client wrapper with retry logic and cost tracking."""

import logging
import time
from typing import Any, Dict, List, Optional

from anthropic import Anthropic, APIError, RateLimitError

from config import get_settings


class AnthropicClient:
    """
    Wrapper around Anthropic API with:
    - Retry logic with exponential backoff
    - Rate limiting
    - Token counting
    - Cost tracking
    """

    # Pricing per million tokens (as of 2025-01-01)
    PRICING = {
        "claude-sonnet-4-20250514": {
            "input": 3.00,  # $3 per million input tokens
            "output": 15.00,  # $15 per million output tokens
        },
        "claude-opus-4-5-20251101": {
            "input": 15.00,
            "output": 75.00,
        },
        "claude-haiku-3-5-20241022": {
            "input": 1.00,
            "output": 5.00,
        },
    }

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize Anthropic client.

        Args:
            api_key: Anthropic API key (defaults to settings)
            model: Model to use (defaults to settings)
        """
        settings = get_settings()
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or settings.anthropic_model
        self.client = Anthropic(api_key=self.api_key)

        self.request_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0

        self.logger = logging.getLogger("calibramark.anthropic")

    def create_message(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_retries: int = 3,
    ) -> Any:
        """
        Create a message with retry logic.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            tools: Optional tool definitions
            max_retries: Maximum number of retry attempts

        Returns:
            Anthropic message response
        """
        for attempt in range(max_retries):
            try:
                params = {
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "messages": messages,
                    "temperature": temperature,
                }

                if system:
                    params["system"] = system

                if tools:
                    params["tools"] = tools

                response = self.client.messages.create(**params)

                # Track usage
                self.request_count += 1
                self.total_input_tokens += response.usage.input_tokens
                self.total_output_tokens += response.usage.output_tokens
                self._track_cost(response.usage.input_tokens, response.usage.output_tokens)

                self.logger.debug(
                    f"API call successful. Tokens: {response.usage.input_tokens} in, "
                    f"{response.usage.output_tokens} out. Total cost: ${self.total_cost:.4f}"
                )

                return response

            except RateLimitError as e:
                if attempt == max_retries - 1:
                    self.logger.error(f"Rate limit exceeded after {max_retries} attempts")
                    raise

                wait_time = 2 ** attempt
                self.logger.warning(f"Rate limit hit, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)

            except APIError as e:
                if attempt == max_retries - 1:
                    self.logger.error(f"API error after {max_retries} attempts: {e}")
                    raise

                wait_time = 2 ** attempt
                self.logger.warning(f"API error, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(wait_time)

            except Exception as e:
                self.logger.error(f"Unexpected error in API call: {e}")
                raise

        raise Exception(f"Failed after {max_retries} attempts")

    def _track_cost(self, input_tokens: int, output_tokens: int) -> None:
        """
        Track cost of API call.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
        """
        if self.model not in self.PRICING:
            self.logger.warning(f"Pricing not available for model {self.model}")
            return

        pricing = self.PRICING[self.model]

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        self.total_cost += input_cost + output_cost

    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get usage statistics.

        Returns:
            Dictionary with usage stats
        """
        return {
            "request_count": self.request_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost": self.total_cost,
            "avg_input_tokens": (
                self.total_input_tokens / self.request_count if self.request_count > 0 else 0
            ),
            "avg_output_tokens": (
                self.total_output_tokens / self.request_count if self.request_count > 0 else 0
            ),
            "avg_cost_per_request": self.total_cost / self.request_count if self.request_count > 0 else 0,
        }

    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self.request_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self.logger.info("Usage statistics reset")
