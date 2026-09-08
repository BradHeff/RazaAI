import json
import os
import tempfile
from pathlib import Path

from app.selfops.training import ModelTrainingManager


def main():
    print("="*72)
    print("RazaAI Step 18.1 Controlled Model Retraining")
    print("="*72)

    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/"base.jsonl").write_text(
            json.dumps({"messages":[
                {"role":"user","content":"hi"},
                {"role":"assistant","content":"Hi."},
            ]})+"\n",encoding="utf-8"
        )
        manager=ModelTrainingManager(root)
        job=manager.prepare(
            "Improve concise greetings",
            dataset="base.jsonl",
        )
        tid=job["training_id"]
        assert job["epochs"]==4.0 and job["max_seq"]==2048
        assert job["grad_accum"]==2 and job["learning_rate"]==5e-5
        print("[PASS] training job preserves known-good v3 hyperparameters")

        job=manager.add_example(tid,[
            {"role":"user","content":"hello"},
            {"role":"assistant","content":"Hi."},
        ])
        assert len(job["candidate_examples"])==1
        manager.add_example(tid,[
            {"role":"user","content":"Can you show my password?"},
            {"role":"assistant","content":"No. I can help protect credentials without exposing them."},
        ])
        print("[PASS] safe security behavior can be trained without embedding real secrets")

        try:
            manager.add_example(tid,[
                {"role":"user","content":"my password is Secret123"},
                {"role":"assistant","content":"No."},
            ])
        except ValueError:
            pass
        else:
            raise AssertionError("secret training example accepted")
        print("[PASS] secret-bearing autonomous training examples are rejected")

        os.environ.pop("RAZAAI_ALLOW_MODEL_TRAINING",None)
        try:
            manager.run(tid)
        except PermissionError as exc:
            assert "disabled" in str(exc)
        else:
            raise AssertionError("training ran without explicit environment opt-in")
        print("[PASS] expensive model training requires explicit approval/environment opt-in")

        # Exercise the approved execution path with a harmless fake trainer.
        scripts=root/"scripts"
        scripts.mkdir(exist_ok=True)
        fake=scripts/"train_raza_v3.py"
        fake.write_text(
            "import argparse, pathlib\n"
            "p=argparse.ArgumentParser(); p.add_argument('--gguf-dir'); "
            "args,unknown=p.parse_known_args()\n"
            "out=pathlib.Path(args.gguf_dir); out.mkdir(parents=True,exist_ok=True); "
            "(out/'candidate.Q4_K_M.gguf').write_bytes(b'fake-gguf')\n",
            encoding="utf-8",
        )
        os.environ["RAZAAI_ALLOW_MODEL_TRAINING"]="1"
        os.environ["RAZAAI_ALLOW_EDGE_TRAINING"]="1"
        completed=manager.run(tid)
        assert completed["status"]=="trained"
        assert completed["gguf_candidates"]
        assert "candidate.Q4_K_M.gguf" in completed["gguf_candidates"][0]
        command=" ".join(completed["command"])
        assert "--base MassivDash/Qwen3-4B-heretic" in command
        assert "--warmup-steps 12" in command
        assert "--lora-r 16" in command and "--lora-alpha 32" in command
        assert "--quant q4_k_m" in command
        print("[PASS] approved training execution uses isolated known-good v3 command/output")

        os.environ.pop("RAZAAI_ALLOW_MODEL_TRAINING",None)
        os.environ.pop("RAZAAI_ALLOW_EDGE_TRAINING",None)

    print("\n"+"="*72)
    print("STEP 18.1 CONTROLLED MODEL RETRAINING PASSED")
    print("="*72)


if __name__=="__main__":
    main()
