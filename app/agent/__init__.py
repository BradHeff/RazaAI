__all__ = ["RazaAgent"]


def __getattr__(name):
    if name == "RazaAgent":
        from .agent import RazaAgent
        return RazaAgent
    raise AttributeError(name)
