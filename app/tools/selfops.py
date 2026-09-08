from __future__ import annotations

from ..selfops import (
    OperationalBriefingEngine,
    OperationalHealthEngine,
    SelfAuditEngine,
    SelfRepairManager,
    ProjectFileBrowser,
)


_AUDIT = SelfAuditEngine()
_REPAIR = SelfRepairManager()
_HEALTH = OperationalHealthEngine()
_BRIEF = OperationalBriefingEngine()
_FILES = ProjectFileBrowser()


def audit_project(mode="quick", check_ollama=True, tests=None):
    report = _AUDIT.run(
        mode=mode,
        check_ollama=bool(check_ollama),
        tests=tests,
    )
    return report.to_dict()


AUDIT_PROJECT_METADATA = {
    "name": "audit_project",
    "category": "selfops",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 300,
    "model_exposed": True,
}

AUDIT_PROJECT_DEFINITION = {
    "type": "function",
    "function": {
        "name": "audit_project",
        "description": (
            "Run a read-only RazaAI self-audit. Compiles project Python, "
            "checks project structure, optionally verifies Ollama/model, and "
            "can run allowlisted tests. Use when asked whether RazaAI itself "
            "is operating correctly or to check its code."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["quick", "full"],
                    "description": "Quick compile/structure audit or full audit with core tests.",
                },
                "check_ollama": {
                    "type": "boolean",
                    "description": "Whether to verify local Ollama and configured model.",
                },
                "tests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional explicit test modules under tests.*.",
                },
            },
            "required": [],
        },
    },
}


def inspect_project_file(file, start_line=1, end_line=240):
    return _REPAIR.inspect(file, start_line, end_line)


INSPECT_PROJECT_FILE_METADATA = {
    "name": "inspect_project_file",
    "category": "selfops",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 10,
    "model_exposed": True,
}

INSPECT_PROJECT_FILE_DEFINITION = {
    "type": "function",
    "function": {
        "name": "inspect_project_file",
        "description": (
            "Read a bounded section of a RazaAI Python source file under "
            "app/, scripts/, or tests/ with line numbers."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["file"],
        },
    },
}


def search_project_code(query, max_results=20):
    return _REPAIR.search(query, max_results=max_results)


SEARCH_PROJECT_CODE_METADATA = {
    "name": "search_project_code",
    "category": "selfops",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 15,
    "model_exposed": True,
}

SEARCH_PROJECT_CODE_DEFINITION = {
    "type": "function",
    "function": {
        "name": "search_project_code",
        "description": (
            "Search RazaAI Python source under app/, scripts/, and tests/ "
            "for a literal code fragment or symbol name."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
}


def investigate_project_code(query, max_files=3, context_lines=100):
    return _REPAIR.investigate(
        query=query,
        max_files=max_files,
        context_lines=context_lines,
    )


INVESTIGATE_PROJECT_CODE_METADATA = {
    "name": "investigate_project_code",
    "category": "selfops",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 20,
    "model_exposed": True,
}

INVESTIGATE_PROJECT_CODE_DEFINITION = {
    "type": "function",
    "function": {
        "name": "investigate_project_code",
        "description": (
            "Locate and inspect the RazaAI source relevant to a natural-language "
            "code-review request. This tool searches before inspecting, so do "
            "not guess a file path when the user names a feature rather than a file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language description of the project area to inspect.",
                },
                "max_files": {"type": "integer"},
                "context_lines": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
}


def search_project_files(query, max_results=20):
    return _FILES.search(query=query, max_results=max_results)


SEARCH_PROJECT_FILES_METADATA = {
    "name": "search_project_files",
    "category": "selfops",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 15,
    "model_exposed": True,
}

SEARCH_PROJECT_FILES_DEFINITION = {
    "type": "function",
    "function": {
        "name": "search_project_files",
        "description": (
            "Search the RazaAI project by filename/path and return metadata only. "
            "Use this for datasets, JSON/JSONL, Markdown, config, or other project "
            "files when the question is about whether a file exists or where it is."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
}


def inspect_project_text_file(file, start_line=1, end_line=200):
    return _FILES.inspect_text(file, start_line=start_line, end_line=end_line)


INSPECT_PROJECT_TEXT_FILE_METADATA = {
    "name": "inspect_project_text_file",
    "category": "selfops",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 15,
    "model_exposed": True,
}

INSPECT_PROJECT_TEXT_FILE_DEFINITION = {
    "type": "function",
    "function": {
        "name": "inspect_project_text_file",
        "description": (
            "Read an approved non-sensitive text file inside the RazaAI project. "
            "Credential/secret-like filenames are blocked. Locate unknown paths with "
            "search_project_files first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["file"],
        },
    },
}

def run_project_test(module):
    return _AUDIT.run_test_module(module)


RUN_PROJECT_TEST_METADATA = {
    "name": "run_project_test",
    "category": "selfops",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 300,
    "model_exposed": True,
}

RUN_PROJECT_TEST_DEFINITION = {
    "type": "function",
    "function": {
        "name": "run_project_test",
        "description": "Run one allowlisted RazaAI Python test module under tests.*.",
        "parameters": {
            "type": "object",
            "properties": {
                "module": {"type": "string"},
            },
            "required": ["module"],
        },
    },
}


def prepare_self_patch(file, old_text, new_text, rationale, tests=None):
    proposal = _REPAIR.propose(
        file=file,
        old_text=old_text,
        new_text=new_text,
        rationale=rationale,
        tests=tests,
    )
    return proposal.to_dict()


PREPARE_SELF_PATCH_METADATA = {
    "name": "prepare_self_patch",
    "category": "selfops",
    "risk": "proposal_only",
    "permission": "automatic",
    "timeout": 20,
    "model_exposed": True,
}

PREPARE_SELF_PATCH_DEFINITION = {
    "type": "function",
    "function": {
        "name": "prepare_self_patch",
        "description": (
            "Prepare, but DO NOT apply, an exact source patch for RazaAI. "
            "The user must explicitly approve applying the returned PATCH-ID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "old_text": {
                    "type": "string",
                    "description": "Exact existing source fragment; must match once.",
                },
                "new_text": {"type": "string"},
                "rationale": {"type": "string"},
                "tests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Targeted tests.* modules to run after application.",
                },
            },
            "required": ["file", "old_text", "new_text", "rationale"],
        },
    },
}


def apply_self_patch(patch_id=None):
    if not patch_id:
        proposal = _REPAIR.latest_proposal()
        if proposal is None:
            raise ValueError("No pending self-repair patch exists.")
        patch_id = proposal.patch_id
    return _REPAIR.apply(patch_id)


APPLY_SELF_PATCH_METADATA = {
    "name": "apply_self_patch",
    "category": "selfops",
    "risk": "source_write",
    "permission": "automatic",
    "timeout": 300,
    "model_exposed": False,
}

APPLY_SELF_PATCH_DEFINITION = {
    "type": "function",
    "function": {
        "name": "apply_self_patch",
        "description": "Hidden explicit-approval self-repair operation.",
        "parameters": {
            "type": "object",
            "properties": {"patch_id": {"type": "string"}},
            "required": [],
        },
    },
}


def rollback_self_patch(patch_id):
    return _REPAIR.rollback(patch_id)


ROLLBACK_SELF_PATCH_METADATA = {
    "name": "rollback_self_patch",
    "category": "selfops",
    "risk": "source_write",
    "permission": "automatic",
    "timeout": 30,
    "model_exposed": False,
}

ROLLBACK_SELF_PATCH_DEFINITION = {
    "type": "function",
    "function": {
        "name": "rollback_self_patch",
        "description": "Hidden explicit-approval rollback operation.",
        "parameters": {
            "type": "object",
            "properties": {"patch_id": {"type": "string"}},
            "required": ["patch_id"],
        },
    },
}


def get_operational_health(run_audit=False, audit_mode="quick"):
    return _HEALTH.snapshot(
        run_audit=bool(run_audit),
        audit_mode=audit_mode,
    )


GET_OPERATIONAL_HEALTH_METADATA = {
    "name": "get_operational_health",
    "category": "selfops",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 300,
    "model_exposed": True,
}

GET_OPERATIONAL_HEALTH_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_operational_health",
        "description": (
            "Return RazaAI operational health: latest self-audit, incident count, "
            "knowledge items needing review/staleness attention, and configured infrastructure count."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "run_audit": {"type": "boolean"},
                "audit_mode": {
                    "type": "string",
                    "enum": ["quick", "full"],
                },
            },
            "required": [],
        },
    },
}


def get_operational_brief(run_audit=False):
    return _BRIEF.build(run_audit=bool(run_audit))


GET_OPERATIONAL_BRIEF_METADATA = {
    "name": "get_operational_brief",
    "category": "selfops",
    "risk": "read_only",
    "permission": "automatic",
    "timeout": 300,
    "model_exposed": True,
}

GET_OPERATIONAL_BRIEF_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_operational_brief",
        "description": (
            "Build a concise proactive operational briefing from trusted RazaAI "
            "self-audit, incident, knowledge-confidence, and inventory state."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "run_audit": {"type": "boolean"},
            },
            "required": [],
        },
    },
}
