"""`python3 -m app.doctor` : read-only health report for a RazaAI device."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from .config import APP_VERSION, APPROVED_CODE_MODEL, BASE_DIR, CODE_MODEL, OLLAMA_HOST, OLLAMA_MODEL, SELFOPS_ENABLED, PROFILE, OLLAMA_NUM_CTX, OLLAMA_NUM_BATCH
from .connectivity import is_online, offline_reason
from .runtime_health import memory_snapshot

OK, WARN, FAIL = "ok", "warn", "fail"


def _check(name, status, detail, fix=None):
    return {"name": name, "status": status, "detail": detail, "fix": fix}


def _ollama_json(path, payload=None, timeout=3):
    req = urllib.request.Request(
        f"{OLLAMA_HOST}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _configured_code_model():
    """Report the effective coding model and configuration source."""
    return CODE_MODEL, "environment" if os.getenv("RAZAAI_CODE_MODEL") else PROFILE.name


def checks():
    out = []
    code_model, code_source = _configured_code_model()

    # Ollama + models
    try:
        tags = _ollama_json("/api/tags")
        names = {m.get("name") for m in tags.get("models", [])}
        out.append(_check("ollama", OK, f"reachable at {OLLAMA_HOST}; {len(names)} model(s)"))
        coder_candidates = [m for m in names if str(m).startswith("raza-coder")]
        if not code_model and coder_candidates:
            out.append(_check("coding model", WARN, f"{coder_candidates[0]} is present but RAZAAI_CODE_MODEL is not set (raza-code would use {OLLAMA_MODEL})",
                              f"add RAZAAI_CODE_MODEL={APPROVED_CODE_MODEL} to /etc/razaai/server.env and ~/.bashrc"))
        for label, model in (("conversation model", OLLAMA_MODEL), ("coding model", code_model or OLLAMA_MODEL)):
            if label == "coding model" and model == OLLAMA_MODEL:
                continue
            present = model in names or any(str(n) == model + ":latest" for n in names)
            if not present:
                out.append(_check(label, FAIL if label == "conversation model" else WARN, f"{model} not present",
                                  f"{PROFILE.model} models"))
                continue
            try:
                show = _ollama_json("/api/show", {"model": model})
                params = str(show.get("parameters") or "")
                caps = show.get("capabilities") or []
                ctx = next((l.split()[1] for l in params.splitlines() if l.strip().startswith("num_ctx")), "?")
                batch = next((l.split()[1] for l in params.splitlines() if l.strip().startswith("num_batch")), "?")
                detail = f"{model}: num_ctx {ctx}, num_batch {batch}, capabilities {','.join(caps) or '?'}" + (f" (from {code_source})" if label == "coding model" else "")
                status = OK if (ctx == str(OLLAMA_NUM_CTX) and batch == str(OLLAMA_NUM_BATCH)) else WARN
                out.append(_check(label, status, detail, None if status == OK else f"{PROFILE.model} models (runtime requests use context {OLLAMA_NUM_CTX}, batch {OLLAMA_NUM_BATCH})"))
            except Exception as exc:  # noqa: BLE001
                out.append(_check(label, WARN, f"{model}: show failed ({exc})"))
        try:
            ps = _ollama_json("/api/ps")
            loaded = [(m.get("name"), round((m.get("size") or 0) / 1e9, 1)) for m in ps.get("models", [])]
            if not loaded:
                out.append(_check("loaded models", WARN, "none resident (first answer will wait for a load)",
                                  "Start the selected launcher to warm the model"))
            elif len(loaded) > 1 and PROFILE.name == "8g":
                out.append(_check("loaded models", WARN, f"{loaded} — more than one resident on an 8 GB device",
                                  "set OLLAMA_MAX_LOADED_MODELS=1 in the Ollama override"))
            else:
                out.append(_check("loaded models", OK, f"{loaded[0][0]} ({loaded[0][1]} GB)"))
        except Exception as exc:  # noqa: BLE001
            out.append(_check("loaded models", WARN, f"ps failed ({exc})"))
    except Exception as exc:  # noqa: BLE001
        out.append(_check("ollama", FAIL, f"unreachable at {OLLAMA_HOST}: {exc}", "sudo systemctl restart ollama"))

    # Ollama runtime env (from the systemd override)
    override = Path("/etc/systemd/system/ollama.service.d/razaai-8g.conf")
    if PROFILE.name != "8g":
        out.append(_check("ollama tuning", OK, "workstation profile; context and batch set per request"))
    elif override.is_file():
        text = override.read_text(encoding="utf-8", errors="replace")
        missing = [k for k in ("OLLAMA_FLASH_ATTENTION=1", "OLLAMA_KV_CACHE_TYPE=q8_0", "OLLAMA_NUM_PARALLEL=1",
                               "OLLAMA_MAX_LOADED_MODELS=1", "LLAMA_ARG_CACHE_RAM=0") if k not in text]
        out.append(_check("ollama tuning", OK if not missing else WARN,
                          "override present" + ("" if not missing else f"; missing {missing}"),
                          None if not missing else "sudo cp deploy/ollama-override.conf /etc/systemd/system/ollama.service.d/override.conf && sudo systemctl daemon-reload && sudo systemctl restart ollama"))
    else:
        out.append(_check("ollama tuning", WARN, "no systemd override (memory growth and swap risk on 8 GB)",
                          "sudo deploy/jetson-headless.sh"))

    # Memory / swap
    snap = memory_snapshot()
    if snap.get("supported"):
        detail = f"{snap['available_mb']} MB available of {snap['total_mb']} MB; swap {snap['swap_used_mb']} MB; {snap.get('model_process') or 'no model process'} {snap.get('model_rss_mb') or 0} MB"
        if snap["swap_used_mb"] > 768 and snap["available_mb"] < 200:
            out.append(_check("memory", FAIL, detail, "Stop competing workloads, then unload unused Ollama models."))
        elif snap["warnings"]:
            out.append(_check("memory", WARN, detail, "Stop competing workloads or unload unused models before retrying."))
        else:
            out.append(_check("memory", OK, detail))
    swapon = _run(["swapon", "--show", "--noheadings"])
    if swapon and swapon.stdout.strip():
        kinds = {line.split()[1] for line in swapon.stdout.strip().splitlines() if len(line.split()) > 1}
        out.append(_check("swap device", OK if "file" not in kinds else WARN, ", ".join(sorted(kinds)),
                          None if "file" not in kinds else "a disk swapfile turns memory pressure into stalls; keep the model resident in RAM"))

    # Disk
    usage = shutil.disk_usage(str(BASE_DIR))
    free_gb = usage.free / 1e9
    out.append(_check("disk", OK if free_gb > 5 else (WARN if free_gb > 2 else FAIL), f"{free_gb:.1f} GB free on {BASE_DIR}",
                      None if free_gb > 5 else "ollama rm unused models; clear output/"))

    # Thermals / power (Jetson)
    temps = []
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            kind = (zone / "type").read_text().strip()
            temp = int((zone / "temp").read_text().strip()) / 1000
            if any(k in kind.lower() for k in ("cpu", "gpu", "soc", "tj")):
                temps.append(f"{kind} {temp:.0f}°C")
        except (OSError, ValueError):
            continue
    if temps:
        hottest = max(float(t.split()[1].rstrip("°C")) for t in temps)
        out.append(_check("thermals", OK if hottest < 75 else WARN, ", ".join(temps[:4]),
                          None if hottest < 75 else "sustained >75°C throttles; check airflow / lower nvpmodel mode"))
    nv = _run(["nvpmodel", "-q"])
    if nv and nv.stdout:
        mode = nv.stdout.strip().splitlines()[0]
        out.append(_check("power mode", OK if "MAXN" in mode else WARN, mode,
                          None if "MAXN" in mode else "Use the power modes documented for your JetPack image and cooling setup."))

    # Connectivity
    online = is_online(refresh=True)
    out.append(_check("internet", OK if online else WARN, "online" if online else f"offline ({offline_reason()}) — web tools answer 'offline' immediately; everything else works"))

    # Sandbox
    try:
        from .tools.workspace import WorkspaceManager
        level, _ = WorkspaceManager.probe_sandbox(refresh=True)
        userns = _run(["sysctl", "-n", "kernel.apparmor_restrict_unprivileged_userns"])
        restricted = bool(userns and userns.stdout.strip() == "1")
        out.append(_check("code sandbox", OK if level == "bwrap" else WARN, f"bubblewrap level: {level}" + ("; userns restricted" if restricted else ""),
                          None if level == "bwrap" else ("sudo apt install -y bubblewrap" if level == "unavailable" else
                                                        "Review the reported sandbox limitation; project checks otherwise run with your OS permissions.")))
    except Exception as exc:  # noqa: BLE001
        out.append(_check("code sandbox", WARN, f"probe failed: {exc}"))

    # Services
    for unit in ("ollama",):
        command = ["systemctl"] + (["--user"] if unit == PROFILE.model else [])
        st = _run(command + ["is-active", unit])
        if st is None:
            continue
        active = st.stdout.strip()
        out.append(_check(f"service {unit}", OK if active == "active" else WARN, active,
                          None if active == "active" else f"systemctl {'--user ' if unit == PROFILE.model else ''}start {unit}"))

    # Knowledge store
    manifest = BASE_DIR / "data" / "knowledge_manifest.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            docs = data.get("documents") or data
            foreign = [k for k in (docs.keys() if isinstance(docs, dict) else []) if isinstance(k, str) and k.startswith("/") and not k.startswith(str(BASE_DIR))]
            out.append(_check("knowledge store", OK if not foreign else WARN,
                              f"{len(docs) if hasattr(docs, '__len__') else '?'} document(s) indexed" + (f"; {len(foreign)} from another machine" if foreign else ""),
                              None if not foreign else "python3 -m scripts.ingest_knowledge"))
        except (ValueError, OSError) as exc:
            out.append(_check("knowledge store", WARN, f"manifest unreadable: {exc}", "python3 -m scripts.ingest_knowledge"))
    else:
        out.append(_check("knowledge store", WARN, "not built", "python3 -m scripts.ingest_knowledge"))

    out.append(_check("self-ops", OK, "locked" if not SELFOPS_ENABLED else "ENABLED (intended only on a workstation)"))
    return out


def render(results):
    icons = {OK: "OK", WARN: "WARN", FAIL: "FAIL"}
    lines = [f"RazaAI doctor: v{APP_VERSION}"]
    for r in results:
        lines.append(f" {icons[r['status']]} {r['name']:18} {r['detail']}")
        if r.get("fix"):
            lines.append(f"      fix: {r['fix']}")
    worst = FAIL if any(r["status"] == FAIL for r in results) else (WARN if any(r["status"] == WARN for r in results) else OK)
    lines.append({OK: "Healthy.", WARN: "Usable, with warnings.", FAIL: "Blocked: fix the FAIL items first."}[worst])
    return "\n".join(lines), {OK: 0, WARN: 1, FAIL: 2}[worst]


def main(argv=None):
    results = checks()
    if argv and "--json" in argv:
        print(json.dumps(results, indent=2))
        return 0
    text, code = render(results)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
