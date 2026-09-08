import os
import platform
import socket


TOOL_METADATA = {
    "name": "get_system_info",
    "category": "system",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 10,
}


def get_system_info():
    """Return read-only information about the system running RazaAI."""

    return {
        "hostname": socket.gethostname(),
        "operating_system": platform.system(),
        "distribution": platform.platform(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python_version": platform.python_version(),
    }


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_system_info",
        "description": (
            "Get read-only information about the computer running "
            "RazaAI, including operating system, kernel, architecture, "
            "CPU count, hostname, and Python version."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}
