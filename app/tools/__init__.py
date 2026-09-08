__all__ = ["ToolRegistry"]


def __getattr__(name):
    if name == "ToolRegistry":
        from .registry import ToolRegistry
        return ToolRegistry
    raise AttributeError(name)
