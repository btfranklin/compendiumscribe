from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from openai import AsyncOpenAI


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
    def __init__(self, openai_client: "AsyncOpenAI | None" = None) -> None:
        self.openai_client = openai_client

    async def run(
        self,
        agent: Any,
        input_payload: str,
        *,
        max_turns: int,
    ) -> AgentRunResult:
        from agents import RunConfig, Runner
        from agents.models.openai_provider import OpenAIProvider

        run_config = None
        if self.openai_client is not None:
            run_config = RunConfig(
                model_provider=OpenAIProvider(
                    openai_client=self.openai_client,
                    use_responses=True,
                )
            )
        result = await Runner.run(
            agent,
            input_payload,
            max_turns=max_turns,
            run_config=run_config,
        )
        return AgentRunResult(final_output=result.final_output, raw_result=result)


__all__ = ["AgentRunResult", "AgentRunner", "OpenAIAgentRunner"]
