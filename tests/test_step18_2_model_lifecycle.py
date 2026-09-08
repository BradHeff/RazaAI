import os
import tempfile
from pathlib import Path

from app.selfops.model_lifecycle import ModelLifecycleManager


class FakeRunner:
    def __init__(self):
        self.commands=[]
    def __call__(self, command, cwd):
        self.commands.append(command)
        text=" ".join(command)
        if "step15_capability_eval" in text:
            return {"success":True,"exit_code":0,
                "stdout":"Capability ready:     YES\nHard-gate failures:   0\nRegression failures:  0\n",
                "stderr":""}
        return {"success":True,"exit_code":0,"stdout":"ok","stderr":""}


def main():
    print("="*72)
    print("RazaAI Step 18.2 GGUF Candidate Lifecycle")
    print("="*72)

    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/"model").mkdir()
        gguf=root/"model/candidate.gguf"; gguf.write_bytes(b"GGUF-test-candidate")
        (root/"Modelfile.raza-edge-v3").write_text(
            "FROM ./model/current.gguf\nPARAMETER num_ctx 4096\nSYSTEM \"\"\"RazaAI\"\"\"\n",
            encoding="utf-8",
        )
        runner=FakeRunner()
        manager=ModelLifecycleManager(root,runner=runner)
        job=manager.stage("model/candidate.gguf")
        mid=job["model_id"]
        assert job["status"]=="staged" and len(job["sha256"])==64
        print("[PASS] GGUF candidate is hashed/staged without replacing active model")

        os.environ["RAZAAI_ALLOW_MODEL_RUNTIME_CHANGES"]="1"
        verified=manager.verify(mid,full=True)
        assert verified["status"]=="verified"
        assert verified["verification"]["capability_ready"] is True
        assert any("raza-candidate:" in " ".join(cmd) for cmd in runner.commands)
        print("[PASS] candidate receives temporary Ollama tag and capability gate")

        promoted=manager.promote(mid)
        assert promoted["status"]=="promoted"
        joined=[" ".join(c) for c in runner.commands]
        assert any("ollama cp raza-edge:4b-v3 " in x and "-backup-" in x for x in joined)
        assert any("ollama cp raza-candidate:" in x and "raza-edge:4b-v3" in x for x in joined)
        print("[PASS] active-model promotion creates rollback tag first")

        rolled=manager.rollback(mid)
        assert rolled["status"]=="rolled_back"
        print("[PASS] active GGUF replacement is reversible")

        os.environ.pop("RAZAAI_ALLOW_MODEL_RUNTIME_CHANGES",None)

    print("\n"+"="*72)
    print("STEP 18.2 GGUF CANDIDATE LIFECYCLE PASSED")
    print("="*72)


if __name__=="__main__":
    main()
