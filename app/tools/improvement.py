from __future__ import annotations

from ..selfops.improvement import SelfImprovementManager
from ..selfops.training import ModelTrainingManager
from ..selfops.model_lifecycle import ModelLifecycleManager
from ..context import CuratedProjectContext

_IMPROVE=SelfImprovementManager(); _TRAIN=ModelTrainingManager()
_MODEL=ModelLifecycleManager(); _CONTEXT=CuratedProjectContext()

def start_self_improvement(goal,targeted_tests=None):
    return _IMPROVE.start(goal,targeted_tests=targeted_tests)
def stage_improvement_patch(improvement_id,file,new_text,rationale,old_text=None,candidate_test=False):
    return _IMPROVE.stage_patch(improvement_id,file=file,old_text=old_text,new_text=new_text,
                                rationale=rationale,candidate_test=bool(candidate_test))
def verify_self_improvement(improvement_id,full=True):
    return _IMPROVE.verify(improvement_id,full=bool(full))
def self_improvement_status(improvement_id=None): return _IMPROVE.status(improvement_id)
def complete_self_improvement_no_change(improvement_id,reason,evidence=None):
    return _IMPROVE.complete_no_change(
        improvement_id,
        reason=reason,
        evidence=evidence,
    )
def promote_self_improvement(improvement_id): return _IMPROVE.promote(improvement_id)
def rollback_self_improvement(improvement_id): return _IMPROVE.rollback(improvement_id)

def prepare_model_training(goal,dataset=None,base_model="MassivDash/Qwen3-4B-heretic",
                           epochs=4.0,max_seq=2048,batch_size=1,grad_accum=2,learning_rate=5e-5):
    return _TRAIN.prepare(goal,dataset=dataset,base_model=base_model,epochs=epochs,max_seq=max_seq,
                          batch_size=batch_size,grad_accum=grad_accum,learning_rate=learning_rate)
def add_model_training_example(training_id,messages): return _TRAIN.add_example(training_id,messages)
def model_training_status(training_id=None): return _TRAIN.status(training_id)
def run_model_training(training_id): return _TRAIN.run(training_id)

def stage_model_candidate(gguf,active_tag=None,modelfile=None):
    return _MODEL.stage(gguf,active_tag=active_tag,modelfile=modelfile)
def verify_model_candidate(model_id,full=True): return _MODEL.verify(model_id,full=bool(full))
def model_candidate_status(model_id=None): return _MODEL.status(model_id)
def promote_model_candidate(model_id): return _MODEL.promote(model_id)
def rollback_model_candidate(model_id): return _MODEL.rollback(model_id)

def project_context_status(): return _CONTEXT.status()
def search_project_context(query,document_request=False,top_k=5):
    matches=_CONTEXT.search(query,document_request=bool(document_request),top_k=top_k)
    return {"query":query,"results":[{"score":score,"path":doc.path,"scope":doc.scope,
            "priority":doc.priority,"content":doc.content[:4000]} for score,doc in matches]}

def _definition(name,description,properties,required=()):
    return {"type":"function","function":{"name":name,"description":description,
            "parameters":{"type":"object","properties":properties,"required":list(required)}}}

def _meta(name,category,risk,timeout=30,exposed=True):
    return {"name":name,"category":category,"risk":risk,"permission":"automatic",
            "timeout":timeout,"model_exposed":exposed}

START_SELF_IMPROVEMENT_METADATA=_meta("start_self_improvement","selfops","sandbox_write",60)
START_SELF_IMPROVEMENT_DEFINITION=_definition("start_self_improvement",
    "Start a sandboxed RazaAI self-improvement job. Production source is unchanged.",
    {"goal":{"type":"string"},"targeted_tests":{"type":"array","items":{"type":"string"}}},("goal",))
STAGE_IMPROVEMENT_PATCH_METADATA=_meta("stage_improvement_patch","selfops","sandbox_write",30)
STAGE_IMPROVEMENT_PATCH_DEFINITION=_definition("stage_improvement_patch",
    "Stage one candidate source change in an improvement sandbox. Existing trusted tests are immutable.",
    {"improvement_id":{"type":"string"},"file":{"type":"string"},"old_text":{"type":"string"},
     "new_text":{"type":"string"},"rationale":{"type":"string"},"candidate_test":{"type":"boolean"}},
    ("improvement_id","file","new_text","rationale"))
VERIFY_SELF_IMPROVEMENT_METADATA=_meta("verify_self_improvement","selfops","sandbox_execution",900)
VERIFY_SELF_IMPROVEMENT_DEFINITION=_definition("verify_self_improvement",
    "Compile and test a staged candidate against baseline/trusted regression tests.",
    {"improvement_id":{"type":"string"},"full":{"type":"boolean"}},("improvement_id",))
SELF_IMPROVEMENT_STATUS_METADATA=_meta("self_improvement_status","selfops","read_only",10)
SELF_IMPROVEMENT_STATUS_DEFINITION=_definition("self_improvement_status","Read improvement job state.",
    {"improvement_id":{"type":"string"}})
COMPLETE_SELF_IMPROVEMENT_NO_CHANGE_METADATA=_meta(
    "complete_self_improvement_no_change","selfops","sandbox_write",10,False
)
COMPLETE_SELF_IMPROVEMENT_NO_CHANGE_DEFINITION=_definition(
    "complete_self_improvement_no_change",
    "Hidden Python-only terminal completion for an evidence-backed no-change improvement job.",
    {
        "improvement_id":{"type":"string"},
        "reason":{"type":"string"},
        "evidence":{"type":"array","items":{"type":"string"}},
    },
    ("improvement_id","reason"),
)
PROMOTE_SELF_IMPROVEMENT_METADATA=_meta("promote_self_improvement","selfops","source_write",900,False)
PROMOTE_SELF_IMPROVEMENT_DEFINITION=_definition("promote_self_improvement",
    "Hidden explicit-approval improvement promotion.",{"improvement_id":{"type":"string"}},("improvement_id",))
ROLLBACK_SELF_IMPROVEMENT_METADATA=_meta("rollback_self_improvement","selfops","source_write",300,False)
ROLLBACK_SELF_IMPROVEMENT_DEFINITION=_definition("rollback_self_improvement",
    "Hidden explicit-approval improvement rollback.",{"improvement_id":{"type":"string"}},("improvement_id",))

PREPARE_MODEL_TRAINING_METADATA=_meta("prepare_model_training","model_training","proposal_only",20)
PREPARE_MODEL_TRAINING_DEFINITION=_definition("prepare_model_training",
    "Prepare a fine-tuning job for an external trainer. Does not run training.",
    {"goal":{"type":"string"},"dataset":{"type":"string"},"base_model":{"type":"string"},
     "epochs":{"type":"number"},"max_seq":{"type":"integer"},"batch_size":{"type":"integer"},
     "grad_accum":{"type":"integer"},"learning_rate":{"type":"number"}},("goal",))
ADD_MODEL_TRAINING_EXAMPLE_METADATA=_meta("add_model_training_example","model_training","dataset_write",20)
ADD_MODEL_TRAINING_EXAMPLE_DEFINITION=_definition("add_model_training_example",
    "Add a non-secret candidate conversation example to a training job.",
    {"training_id":{"type":"string"},"messages":{"type":"array","items":{"type":"object"}}},
    ("training_id","messages"))
MODEL_TRAINING_STATUS_METADATA=_meta("model_training_status","model_training","read_only",10)
MODEL_TRAINING_STATUS_DEFINITION=_definition("model_training_status","Read training job state.",
    {"training_id":{"type":"string"}})
RUN_MODEL_TRAINING_METADATA=_meta("run_model_training","model_training","gpu_training",86400,False)
RUN_MODEL_TRAINING_DEFINITION=_definition("run_model_training","Hidden explicit-approval training execution.",
    {"training_id":{"type":"string"}},("training_id",))

STAGE_MODEL_CANDIDATE_METADATA=_meta("stage_model_candidate","model_lifecycle","proposal_only",120)
STAGE_MODEL_CANDIDATE_DEFINITION=_definition("stage_model_candidate",
    "Stage a GGUF candidate without replacing the active model.",
    {"gguf":{"type":"string"},"active_tag":{"type":"string"},"modelfile":{"type":"string"}},("gguf",))
VERIFY_MODEL_CANDIDATE_METADATA=_meta("verify_model_candidate","model_lifecycle","candidate_runtime",7200)
VERIFY_MODEL_CANDIDATE_DEFINITION=_definition("verify_model_candidate",
    "Create/evaluate a temporary Ollama candidate tag; active model is unchanged.",
    {"model_id":{"type":"string"},"full":{"type":"boolean"}},("model_id",))
MODEL_CANDIDATE_STATUS_METADATA=_meta("model_candidate_status","model_lifecycle","read_only",10)
MODEL_CANDIDATE_STATUS_DEFINITION=_definition("model_candidate_status","Read model candidate state.",
    {"model_id":{"type":"string"}})
PROMOTE_MODEL_CANDIDATE_METADATA=_meta("promote_model_candidate","model_lifecycle","active_model_replace",600,False)
PROMOTE_MODEL_CANDIDATE_DEFINITION=_definition("promote_model_candidate",
    "Hidden explicit-approval active model promotion.",{"model_id":{"type":"string"}},("model_id",))
ROLLBACK_MODEL_CANDIDATE_METADATA=_meta("rollback_model_candidate","model_lifecycle","active_model_replace",600,False)
ROLLBACK_MODEL_CANDIDATE_DEFINITION=_definition("rollback_model_candidate",
    "Hidden explicit-approval active model rollback.",{"model_id":{"type":"string"}},("model_id",))

PROJECT_CONTEXT_STATUS_METADATA=_meta("project_context_status","knowledge","read_only",10)
PROJECT_CONTEXT_STATUS_DEFINITION=_definition("project_context_status",
    "List curated Markdown context and detected document theme.",{})
SEARCH_PROJECT_CONTEXT_METADATA=_meta("search_project_context","knowledge","read_only",10)
SEARCH_PROJECT_CONTEXT_DEFINITION=_definition("search_project_context",
    "Search operator-curated Markdown such as BRANDING.md and knowledge/project/*.md.",
    {"query":{"type":"string"},"document_request":{"type":"boolean"},"top_k":{"type":"integer"}},("query",))
