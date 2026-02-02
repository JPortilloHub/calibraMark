"""Base agent class for CalibraMark pipeline agents."""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from utils.anthropic_client import AnthropicClient
from utils.data_storage import DataStorage


class BaseAgent(ABC):
    """
    Abstract base class for CalibraMark agents.

    Agents are Python orchestrators that:
    1. Fetch data from MCP servers
    2. Prepare context for Claude Code skills
    3. Invoke Claude via Anthropic API with skill prompts
    4. Parse structured outputs
    5. Make decisions based on skill recommendations
    """

    def __init__(
        self,
        name: str,
        client: Optional[AnthropicClient] = None,
        storage: Optional[DataStorage] = None,
    ):
        self.name = name
        self.client = client or AnthropicClient()
        self.storage = storage or DataStorage()
        self.logger = logging.getLogger(f"calibramark.agent.{name}")

    def _load_skill(self, skill_name: str) -> str:
        """Load a Claude Code skill prompt from disk."""
        skill_path = Path(f".claude/skills/{skill_name}/SKILL.md")
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill not found: {skill_path}")

        content = skill_path.read_text()

        # Strip YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()

        return content.strip()

    def _invoke_skill(
        self,
        skill_name: str,
        context: str,
        max_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> str:
        """
        Invoke a Claude Code skill with context.

        Args:
            skill_name: Name of the skill in .claude/skills/
            context: Context to send along with the skill prompt
            max_tokens: Max response tokens
            temperature: Sampling temperature

        Returns:
            Claude's response text
        """
        skill_prompt = self._load_skill(skill_name)

        response = self.client.create_message(
            messages=[{"role": "user", "content": context}],
            system=skill_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Extract text from response
        for block in response.content:
            if block.type == "text":
                return block.text

        return ""

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Extract JSON from a Claude response that may contain markdown."""
        # Try parsing the whole text first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Look for JSON in code blocks
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            return json.loads(text[start:end].strip())

        if "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            candidate = text[start:end].strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # Look for { ... } blocks
        brace_start = text.find("{")
        if brace_start != -1:
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[brace_start : i + 1])
                        except json.JSONDecodeError:
                            break

        raise ValueError(f"Could not parse JSON from response: {text[:200]}...")

    def _save_decision(
        self,
        market_id: str,
        decision: Dict[str, Any],
    ) -> None:
        """Save an agent decision to storage."""
        self.storage.save_agent_decision(
            market_id=market_id,
            agent_name=self.name,
            decision=decision,
        )

    @abstractmethod
    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the agent. Subclasses must implement this."""
        ...
