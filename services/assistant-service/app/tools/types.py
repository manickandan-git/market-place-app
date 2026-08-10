from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolContext:
    request_id: str | None
    access_token: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict, ToolContext], Awaitable[dict]]
    is_write: bool = False

    def to_anthropic_tool(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

