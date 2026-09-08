"""RazaAI:  project file search prefers the shallowest exact-name match."""

import tempfile
from pathlib import Path

from app.selfops.files import ProjectFileBrowser


def main():
    print("=" * 78)
    print("RazaAI Step 20.8.7 File Search Ranking")
    print("=" * 78)

    root = Path(tempfile.mkdtemp())
    (root / "raza_train_v3.jsonl").write_text("{}\n", encoding="utf-8")
    # Nested copies whose paths sort *before* the root file alphabetically.
    for nested in ("RazaAI_adapter_v3/export", "data/model_training/jobs/j1", "Archive"):
        (root / nested).mkdir(parents=True)
        (root / nested / "raza_train_v3.jsonl").write_text("{}\n", encoding="utf-8")

    found = ProjectFileBrowser(root).search("raza_train_v3.jsonl", max_results=5)
    assert found["found"]
    assert found["results"][0]["file"] == "raza_train_v3.jsonl", found["results"]
    print("[PASS] root-level exact match outranks nested copies regardless of path spelling")

    files = [item["file"] for item in found["results"]]
    assert "Archive/raza_train_v3.jsonl" in files and "RazaAI_adapter_v3/export/raza_train_v3.jsonl" in files
    print("[PASS] nested copies are still returned, just ranked lower")

    only_nested = Path(tempfile.mkdtemp())
    (only_nested / "deep/er/path").mkdir(parents=True)
    (only_nested / "deep/er/path/Modelfile.x").write_text("FROM x\n", encoding="utf-8")
    (only_nested / "notes.md").write_text("Modelfile mention\n", encoding="utf-8")
    result = ProjectFileBrowser(only_nested).search("Modelfile.x", max_results=3)
    assert result["results"][0]["file"] == "deep/er/path/Modelfile.x", result["results"]
    print("[PASS] depth penalty never lets a weak shallow match beat a deep exact match")

    print("=" * 78)
    print("STEP 20.8.7 FILE SEARCH RANKING PASSED")
    print("=" * 78)


if __name__ == "__main__":
    main()
