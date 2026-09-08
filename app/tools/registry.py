import time
from .system import get_system_info, TOOL_DEFINITION as SYSTEM_INFO_DEFINITION, TOOL_METADATA as SYSTEM_INFO_METADATA
from .network import get_network_interfaces, NETWORK_INTERFACE_DEFINITION, TOOL_METADATA as NETWORK_INTERFACE_METADATA
from .ip_config import get_ip_configuration, IP_CONFIGURATION_DEFINITION, TOOL_METADATA as IP_CONFIGURATION_METADATA
from .routing import get_routing_table, ROUTING_TABLE_DEFINITION, ROUTING_TABLE_METADATA
from .dns import dns_lookup, DNS_LOOKUP_DEFINITION, DNS_LOOKUP_METADATA
from .ping import ping_host, PING_DEFINITION, PING_METADATA
from .knowledge import search_knowledge, KNOWLEDGE_SEARCH_DEFINITION, KNOWLEDGE_SEARCH_METADATA
from .result import ToolResult
from .execution import ToolDeadlineExceeded, tool_deadline
from .web import (
    search_web,
    WEB_SEARCH_DEFINITION,
    WEB_SEARCH_METADATA,
    fetch_web_page,
    WEB_FETCH_DEFINITION,
    WEB_FETCH_METADATA,
)
from .memory import (
    remember_memory,
    MEMORY_REMEMBER_DEFINITION,
    MEMORY_REMEMBER_METADATA,
    search_memory,
    MEMORY_SEARCH_DEFINITION,
    MEMORY_SEARCH_METADATA,
    get_identity_profile,
    IDENTITY_PROFILE_DEFINITION,
    IDENTITY_PROFILE_METADATA,
    memory_status,
    MEMORY_STATUS_DEFINITION,
    MEMORY_STATUS_METADATA,
    forget_memory,
    MEMORY_FORGET_DEFINITION,
    MEMORY_FORGET_METADATA,
)
from .infrastructure import (
    list_infrastructure,
    LIST_INFRASTRUCTURE_DEFINITION,
    LIST_INFRASTRUCTURE_METADATA,
    run_infrastructure_check,
    RUN_INFRASTRUCTURE_CHECK_DEFINITION,
    RUN_INFRASTRUCTURE_CHECK_METADATA,
)
from .aruba_port import (
    inspect_aruba_port,
    ARUBA_PORT_DEFINITION,
    ARUBA_PORT_METADATA,
)
from .aruba_diagnostic import (
    diagnose_aruba_port,
    ARUBA_PORT_DIAGNOSTIC_DEFINITION,
    ARUBA_PORT_DIAGNOSTIC_METADATA,
)
from ..config import SELFOPS_ENABLED, SELF_MODIFYING_RISKS
from .selfops import (
    audit_project,
    AUDIT_PROJECT_DEFINITION,
    AUDIT_PROJECT_METADATA,
    inspect_project_file,
    INSPECT_PROJECT_FILE_DEFINITION,
    INSPECT_PROJECT_FILE_METADATA,
    search_project_code,
    SEARCH_PROJECT_CODE_DEFINITION,
    SEARCH_PROJECT_CODE_METADATA,
    investigate_project_code,
    INVESTIGATE_PROJECT_CODE_DEFINITION,
    INVESTIGATE_PROJECT_CODE_METADATA,
    search_project_files,
    SEARCH_PROJECT_FILES_DEFINITION,
    SEARCH_PROJECT_FILES_METADATA,
    inspect_project_text_file,
    INSPECT_PROJECT_TEXT_FILE_DEFINITION,
    INSPECT_PROJECT_TEXT_FILE_METADATA,
    run_project_test,
    RUN_PROJECT_TEST_DEFINITION,
    RUN_PROJECT_TEST_METADATA,
    prepare_self_patch,
    PREPARE_SELF_PATCH_DEFINITION,
    PREPARE_SELF_PATCH_METADATA,
    apply_self_patch,
    APPLY_SELF_PATCH_DEFINITION,
    APPLY_SELF_PATCH_METADATA,
    rollback_self_patch,
    ROLLBACK_SELF_PATCH_DEFINITION,
    ROLLBACK_SELF_PATCH_METADATA,
    get_operational_health,
    GET_OPERATIONAL_HEALTH_DEFINITION,
    GET_OPERATIONAL_HEALTH_METADATA,
    get_operational_brief,
    GET_OPERATIONAL_BRIEF_DEFINITION,
    GET_OPERATIONAL_BRIEF_METADATA,
)
from .improvement import (
    start_self_improvement, START_SELF_IMPROVEMENT_DEFINITION, START_SELF_IMPROVEMENT_METADATA,
    stage_improvement_patch, STAGE_IMPROVEMENT_PATCH_DEFINITION, STAGE_IMPROVEMENT_PATCH_METADATA,
    verify_self_improvement, VERIFY_SELF_IMPROVEMENT_DEFINITION, VERIFY_SELF_IMPROVEMENT_METADATA,
    self_improvement_status, SELF_IMPROVEMENT_STATUS_DEFINITION, SELF_IMPROVEMENT_STATUS_METADATA,
    complete_self_improvement_no_change, COMPLETE_SELF_IMPROVEMENT_NO_CHANGE_DEFINITION, COMPLETE_SELF_IMPROVEMENT_NO_CHANGE_METADATA,
    promote_self_improvement, PROMOTE_SELF_IMPROVEMENT_DEFINITION, PROMOTE_SELF_IMPROVEMENT_METADATA,
    rollback_self_improvement, ROLLBACK_SELF_IMPROVEMENT_DEFINITION, ROLLBACK_SELF_IMPROVEMENT_METADATA,
    prepare_model_training, PREPARE_MODEL_TRAINING_DEFINITION, PREPARE_MODEL_TRAINING_METADATA,
    add_model_training_example, ADD_MODEL_TRAINING_EXAMPLE_DEFINITION, ADD_MODEL_TRAINING_EXAMPLE_METADATA,
    model_training_status, MODEL_TRAINING_STATUS_DEFINITION, MODEL_TRAINING_STATUS_METADATA,
    run_model_training, RUN_MODEL_TRAINING_DEFINITION, RUN_MODEL_TRAINING_METADATA,
    stage_model_candidate, STAGE_MODEL_CANDIDATE_DEFINITION, STAGE_MODEL_CANDIDATE_METADATA,
    verify_model_candidate, VERIFY_MODEL_CANDIDATE_DEFINITION, VERIFY_MODEL_CANDIDATE_METADATA,
    model_candidate_status, MODEL_CANDIDATE_STATUS_DEFINITION, MODEL_CANDIDATE_STATUS_METADATA,
    promote_model_candidate, PROMOTE_MODEL_CANDIDATE_DEFINITION, PROMOTE_MODEL_CANDIDATE_METADATA,
    rollback_model_candidate, ROLLBACK_MODEL_CANDIDATE_DEFINITION, ROLLBACK_MODEL_CANDIDATE_METADATA,
    project_context_status, PROJECT_CONTEXT_STATUS_DEFINITION, PROJECT_CONTEXT_STATUS_METADATA,
    search_project_context, SEARCH_PROJECT_CONTEXT_DEFINITION, SEARCH_PROJECT_CONTEXT_METADATA,
)
from .workspace import (
    WorkspaceManager,
    WORKSPACE_STATUS_DEFINITION, WORKSPACE_STATUS_METADATA,
    WORKSPACE_LIST_DEFINITION, WORKSPACE_LIST_METADATA,
    WORKSPACE_READ_DEFINITION, WORKSPACE_READ_METADATA,
    WORKSPACE_SEARCH_DEFINITION, WORKSPACE_SEARCH_METADATA,
    WORKSPACE_MKDIR_DEFINITION, WORKSPACE_MKDIR_METADATA,
    WORKSPACE_WRITE_DEFINITION, WORKSPACE_WRITE_METADATA,
    WORKSPACE_PATCH_DEFINITION, WORKSPACE_PATCH_METADATA,
    WORKSPACE_RUN_DEFINITION, WORKSPACE_RUN_METADATA,
    WORKSPACE_GIT_STATUS_DEFINITION, WORKSPACE_GIT_STATUS_METADATA,
    WORKSPACE_GIT_DIFF_DEFINITION, WORKSPACE_GIT_DIFF_METADATA,
)
from .documents import (
    create_document,
    CREATE_DOCUMENT_DEFINITION,
    CREATE_DOCUMENT_METADATA,
    list_document_templates,
    LIST_DOCUMENT_TEMPLATES_DEFINITION,
    LIST_DOCUMENT_TEMPLATES_METADATA,
    list_generated_documents,
    LIST_GENERATED_DOCUMENTS_DEFINITION,
    LIST_GENERATED_DOCUMENTS_METADATA,
)

class ToolRegistry:
    def __init__(self, workspace_root=None):
        self.workspace = WorkspaceManager(workspace_root) if workspace_root is not None else None
        self._tools={
            "get_system_info":{"function":get_system_info,"definition":SYSTEM_INFO_DEFINITION,"metadata":SYSTEM_INFO_METADATA},
            "get_network_interfaces":{"function":get_network_interfaces,"definition":NETWORK_INTERFACE_DEFINITION,"metadata":NETWORK_INTERFACE_METADATA},
            "get_ip_configuration":{"function":get_ip_configuration,"definition":IP_CONFIGURATION_DEFINITION,"metadata":IP_CONFIGURATION_METADATA},
            "get_routing_table":{"function":get_routing_table,"definition":ROUTING_TABLE_DEFINITION,"metadata":ROUTING_TABLE_METADATA},
            "dns_lookup":{"function":dns_lookup,"definition":DNS_LOOKUP_DEFINITION,"metadata":DNS_LOOKUP_METADATA},
            "ping_host":{"function":ping_host,"definition":PING_DEFINITION,"metadata":PING_METADATA},
            "search_knowledge":{"function":search_knowledge,"definition":KNOWLEDGE_SEARCH_DEFINITION,"metadata":KNOWLEDGE_SEARCH_METADATA},
            "search_web": {
                "function": search_web,
                "definition": WEB_SEARCH_DEFINITION,
                "metadata": WEB_SEARCH_METADATA,
            },
            "fetch_web_page": {
                "function": fetch_web_page,
                "definition": WEB_FETCH_DEFINITION,
                "metadata": WEB_FETCH_METADATA,
            },
            "remember_memory": {
                "function": remember_memory,
                "definition": MEMORY_REMEMBER_DEFINITION,
                "metadata": MEMORY_REMEMBER_METADATA,
            },
            "search_memory": {
                "function": search_memory,
                "definition": MEMORY_SEARCH_DEFINITION,
                "metadata": MEMORY_SEARCH_METADATA,
            },
            "get_identity_profile": {
                "function": get_identity_profile,
                "definition": IDENTITY_PROFILE_DEFINITION,
                "metadata": IDENTITY_PROFILE_METADATA,
            },
            "memory_status": {
                "function": memory_status,
                "definition": MEMORY_STATUS_DEFINITION,
                "metadata": MEMORY_STATUS_METADATA,
            },
            "forget_memory": {
                "function": forget_memory,
                "definition": MEMORY_FORGET_DEFINITION,
                "metadata": MEMORY_FORGET_METADATA,
            },
            "list_infrastructure": {
                "function": list_infrastructure,
                "definition": LIST_INFRASTRUCTURE_DEFINITION,
                "metadata": LIST_INFRASTRUCTURE_METADATA,
            },

            "run_infrastructure_check": {
                "function": run_infrastructure_check,
                "definition": RUN_INFRASTRUCTURE_CHECK_DEFINITION,
                "metadata": RUN_INFRASTRUCTURE_CHECK_METADATA,
            },
            "inspect_aruba_port": {
                "function": inspect_aruba_port,
                "definition": ARUBA_PORT_DEFINITION,
                "metadata": ARUBA_PORT_METADATA,
            },
            "diagnose_aruba_port": {
                "function": diagnose_aruba_port,
                "definition": ARUBA_PORT_DIAGNOSTIC_DEFINITION,
                "metadata": ARUBA_PORT_DIAGNOSTIC_METADATA,
            },
            "create_document": {
                "function": create_document,
                "definition": CREATE_DOCUMENT_DEFINITION,
                "metadata": CREATE_DOCUMENT_METADATA,
            },
            "list_document_templates": {
                "function": list_document_templates,
                "definition": LIST_DOCUMENT_TEMPLATES_DEFINITION,
                "metadata": LIST_DOCUMENT_TEMPLATES_METADATA,
            },

            "audit_project": {
                "function": audit_project,
                "definition": AUDIT_PROJECT_DEFINITION,
                "metadata": AUDIT_PROJECT_METADATA,
            },
            "inspect_project_file": {
                "function": inspect_project_file,
                "definition": INSPECT_PROJECT_FILE_DEFINITION,
                "metadata": INSPECT_PROJECT_FILE_METADATA,
            },
            "search_project_code": {
                "function": search_project_code,
                "definition": SEARCH_PROJECT_CODE_DEFINITION,
                "metadata": SEARCH_PROJECT_CODE_METADATA,
            },
            "investigate_project_code": {
                "function": investigate_project_code,
                "definition": INVESTIGATE_PROJECT_CODE_DEFINITION,
                "metadata": INVESTIGATE_PROJECT_CODE_METADATA,
            },
            "search_project_files": {
                "function": search_project_files,
                "definition": SEARCH_PROJECT_FILES_DEFINITION,
                "metadata": SEARCH_PROJECT_FILES_METADATA,
            },
            "inspect_project_text_file": {
                "function": inspect_project_text_file,
                "definition": INSPECT_PROJECT_TEXT_FILE_DEFINITION,
                "metadata": INSPECT_PROJECT_TEXT_FILE_METADATA,
            },
            "run_project_test": {
                "function": run_project_test,
                "definition": RUN_PROJECT_TEST_DEFINITION,
                "metadata": RUN_PROJECT_TEST_METADATA,
            },
            "prepare_self_patch": {
                "function": prepare_self_patch,
                "definition": PREPARE_SELF_PATCH_DEFINITION,
                "metadata": PREPARE_SELF_PATCH_METADATA,
            },
            "apply_self_patch": {
                "function": apply_self_patch,
                "definition": APPLY_SELF_PATCH_DEFINITION,
                "metadata": APPLY_SELF_PATCH_METADATA,
            },
            "rollback_self_patch": {
                "function": rollback_self_patch,
                "definition": ROLLBACK_SELF_PATCH_DEFINITION,
                "metadata": ROLLBACK_SELF_PATCH_METADATA,
            },
            "get_operational_health": {
                "function": get_operational_health,
                "definition": GET_OPERATIONAL_HEALTH_DEFINITION,
                "metadata": GET_OPERATIONAL_HEALTH_METADATA,
            },
            "get_operational_brief": {
                "function": get_operational_brief,
                "definition": GET_OPERATIONAL_BRIEF_DEFINITION,
                "metadata": GET_OPERATIONAL_BRIEF_METADATA,
            },
            "list_generated_documents": {
                "function": list_generated_documents,
                "definition": LIST_GENERATED_DOCUMENTS_DEFINITION,
                "metadata": LIST_GENERATED_DOCUMENTS_METADATA,
            },
            "start_self_improvement": {"function":start_self_improvement,"definition":START_SELF_IMPROVEMENT_DEFINITION,"metadata":START_SELF_IMPROVEMENT_METADATA},
            "stage_improvement_patch": {"function":stage_improvement_patch,"definition":STAGE_IMPROVEMENT_PATCH_DEFINITION,"metadata":STAGE_IMPROVEMENT_PATCH_METADATA},
            "verify_self_improvement": {"function":verify_self_improvement,"definition":VERIFY_SELF_IMPROVEMENT_DEFINITION,"metadata":VERIFY_SELF_IMPROVEMENT_METADATA},
            "self_improvement_status": {"function":self_improvement_status,"definition":SELF_IMPROVEMENT_STATUS_DEFINITION,"metadata":SELF_IMPROVEMENT_STATUS_METADATA},
            "complete_self_improvement_no_change": {"function":complete_self_improvement_no_change,"definition":COMPLETE_SELF_IMPROVEMENT_NO_CHANGE_DEFINITION,"metadata":COMPLETE_SELF_IMPROVEMENT_NO_CHANGE_METADATA},
            "promote_self_improvement": {"function":promote_self_improvement,"definition":PROMOTE_SELF_IMPROVEMENT_DEFINITION,"metadata":PROMOTE_SELF_IMPROVEMENT_METADATA},
            "rollback_self_improvement": {"function":rollback_self_improvement,"definition":ROLLBACK_SELF_IMPROVEMENT_DEFINITION,"metadata":ROLLBACK_SELF_IMPROVEMENT_METADATA},
            "prepare_model_training": {"function":prepare_model_training,"definition":PREPARE_MODEL_TRAINING_DEFINITION,"metadata":PREPARE_MODEL_TRAINING_METADATA},
            "add_model_training_example": {"function":add_model_training_example,"definition":ADD_MODEL_TRAINING_EXAMPLE_DEFINITION,"metadata":ADD_MODEL_TRAINING_EXAMPLE_METADATA},
            "model_training_status": {"function":model_training_status,"definition":MODEL_TRAINING_STATUS_DEFINITION,"metadata":MODEL_TRAINING_STATUS_METADATA},
            "run_model_training": {"function":run_model_training,"definition":RUN_MODEL_TRAINING_DEFINITION,"metadata":RUN_MODEL_TRAINING_METADATA},
            "stage_model_candidate": {"function":stage_model_candidate,"definition":STAGE_MODEL_CANDIDATE_DEFINITION,"metadata":STAGE_MODEL_CANDIDATE_METADATA},
            "verify_model_candidate": {"function":verify_model_candidate,"definition":VERIFY_MODEL_CANDIDATE_DEFINITION,"metadata":VERIFY_MODEL_CANDIDATE_METADATA},
            "model_candidate_status": {"function":model_candidate_status,"definition":MODEL_CANDIDATE_STATUS_DEFINITION,"metadata":MODEL_CANDIDATE_STATUS_METADATA},
            "promote_model_candidate": {"function":promote_model_candidate,"definition":PROMOTE_MODEL_CANDIDATE_DEFINITION,"metadata":PROMOTE_MODEL_CANDIDATE_METADATA},
            "rollback_model_candidate": {"function":rollback_model_candidate,"definition":ROLLBACK_MODEL_CANDIDATE_DEFINITION,"metadata":ROLLBACK_MODEL_CANDIDATE_METADATA},
            "project_context_status": {"function":project_context_status,"definition":PROJECT_CONTEXT_STATUS_DEFINITION,"metadata":PROJECT_CONTEXT_STATUS_METADATA},
            "search_project_context": {"function":search_project_context,"definition":SEARCH_PROJECT_CONTEXT_DEFINITION,"metadata":SEARCH_PROJECT_CONTEXT_METADATA},
        }

        if self.workspace is not None:
            manager = self.workspace
            self._tools.update({
                "workspace_status": {
                    "function": manager.status,
                    "definition": WORKSPACE_STATUS_DEFINITION,
                    "metadata": WORKSPACE_STATUS_METADATA,
                },
                "workspace_list": {
                    "function": manager.list_files,
                    "definition": WORKSPACE_LIST_DEFINITION,
                    "metadata": WORKSPACE_LIST_METADATA,
                },
                "workspace_read_file": {
                    "function": manager.read_file,
                    "definition": WORKSPACE_READ_DEFINITION,
                    "metadata": WORKSPACE_READ_METADATA,
                },
                "workspace_search": {
                    "function": manager.search,
                    "definition": WORKSPACE_SEARCH_DEFINITION,
                    "metadata": WORKSPACE_SEARCH_METADATA,
                },
                "workspace_mkdir": {
                    "function": manager.mkdir,
                    "definition": WORKSPACE_MKDIR_DEFINITION,
                    "metadata": WORKSPACE_MKDIR_METADATA,
                },
                "workspace_write_file": {
                    "function": manager.write_file,
                    "definition": WORKSPACE_WRITE_DEFINITION,
                    "metadata": WORKSPACE_WRITE_METADATA,
                },
                "workspace_patch_file": {
                    "function": manager.patch_file,
                    "definition": WORKSPACE_PATCH_DEFINITION,
                    "metadata": WORKSPACE_PATCH_METADATA,
                },
                "workspace_run_command": {
                    "function": manager.run_command,
                    "definition": WORKSPACE_RUN_DEFINITION,
                    "metadata": WORKSPACE_RUN_METADATA,
                },
                "workspace_git_status": {
                    "function": manager.git_status,
                    "definition": WORKSPACE_GIT_STATUS_DEFINITION,
                    "metadata": WORKSPACE_GIT_STATUS_METADATA,
                },
                "workspace_git_diff": {
                    "function": manager.git_diff,
                    "definition": WORKSPACE_GIT_DIFF_DEFINITION,
                    "metadata": WORKSPACE_GIT_DIFF_METADATA,
                },
            })

    def get_definitions(self, *, categories=None, names=None):
        """Return only model-exposed definitions relevant to the current turn."""
        categories = set(categories or ())
        names = set(names or ())
        definitions = []
        for name, tool in self._tools.items():
            metadata = tool["metadata"]
            if not metadata.get("model_exposed", True):
                continue
            if self.is_self_modifying(name) and not self.selfops_enabled:
                continue
            if names and name not in names:
                continue
            if categories and metadata.get("category") not in categories:
                continue
            definitions.append(tool["definition"])
        return definitions
    selfops_enabled = SELFOPS_ENABLED

    def is_self_modifying(self, name):
        """True for tools that change RazaAI's own code, datasets or model."""
        tool = self._tools.get(name)
        if not tool:
            return False
        return tool["metadata"].get("risk") in SELF_MODIFYING_RISKS

    def get_metadata(self,name):
        if name not in self._tools: raise ValueError(f"Unknown RazaAI tool: {name}")
        return self._tools[name]["metadata"]
    def list_tools(self): return [t["metadata"] for t in self._tools.values()]
    def execute(self,name,arguments=None):
        start=time.perf_counter()
        if name not in self._tools: return ToolResult(False,name,error=f"Unknown RazaAI tool: {name}",execution_time=time.perf_counter()-start)
        tool=self._tools[name]; meta=tool["metadata"]
        if self.is_self_modifying(name) and not self.selfops_enabled:
            return ToolResult(False,name,error=(
                f"Self-modification tool '{name}' is disabled on this build "
                "(RAZAAI_SELFOPS is not enabled). Read-only self-audit remains available."
            ),execution_time=time.perf_counter()-start)
        if meta["permission"]!="automatic": return ToolResult(False,name,error=f"Tool requires permission: {meta['permission']}",execution_time=time.perf_counter()-start)
        timeout=max(1,int(meta.get("timeout") or 1))
        try:
            with tool_deadline(timeout):
                result=tool["function"](**(arguments or {}))
            elapsed=time.perf_counter()-start
            # Fallback enforcement for non-main-thread/non-POSIX execution. It
            # cannot interrupt the call, but still prevents a late result from
            # being treated as successful.
            if elapsed>timeout: return ToolResult(False,name,error=f"Tool exceeded timeout of {timeout} seconds",execution_time=elapsed)
            return ToolResult(True,name,result=result,execution_time=elapsed)
        except ToolDeadlineExceeded:
            return ToolResult(False,name,error=f"Tool exceeded hard timeout of {timeout} seconds",execution_time=time.perf_counter()-start)
        except Exception as exc: return ToolResult(False,name,error=str(exc),execution_time=time.perf_counter()-start)
