from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentRunResult:
    final_output: Any
    raw_result: Any

    @property
    def response_ids(self) -> list[str]:
        ids: list[str] = []
        for response in getattr(self.raw_result, "raw_responses", []) or []:
            response_id = getattr(response, "response_id", None)
            if response_id:
                ids.append(str(response_id))
        return ids


class AgentRunner(Protocol):
    async def run(
        self,
        agent: Any,
        input_payload: str,
        *,
        max_turns: int,
    ) -> AgentRunResult:
        ...


class OpenAIAgentRunner:
    async def run(
        self,
        agent: Any,
        input_payload: str,
        *,
        max_turns: int,
    ) -> AgentRunResult:
        from agents import Runner

        result = await Runner.run(agent, input_payload, max_turns=max_turns)
        return AgentRunResult(final_output=result.final_output, raw_result=result)


__all__ = ["AgentRunResult", "AgentRunner", "OpenAIAgentRunner"]
