from dataclasses import dataclass, asdict
from typing import Any
import time


@dataclass
class ToolResult:
    """Standard result returned by every RazaAI tool execution."""

    success: bool
    tool: str
    result: Any = None
    error: str | None = None
    execution_time: float = 0.0

    def to_dict(self):
        return asdict(self)

    def to_text(self):
        """Convert the result into a representation suitable for returning to the language model."""

        if self.success:
            return str(self.result)

        return f"Tool execution failed: {self.error}"
