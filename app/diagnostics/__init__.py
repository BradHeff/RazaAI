"""Diagnostics package."""

__all__ = ["DiagnosticEngine", "DiagnosticContext"]


def __getattr__(name):
    if name in {"DiagnosticEngine", "DiagnosticContext"}:
        from .engine import DiagnosticContext, DiagnosticEngine
        return {"DiagnosticEngine": DiagnosticEngine, "DiagnosticContext": DiagnosticContext}[name]
    raise AttributeError(name)
