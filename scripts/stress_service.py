"""RazaAI stress test : the service under concurrent sessions (.x)."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RESULTS = Path("evals/stress/results")

CONVERSATION = [
    ("identity", "who made you?", lambda a: "brad heffernan" in a.casefold()),
    ("identity-when", "when were you created?", lambda a: "2019" in a),
    ("challenge", "liar", lambda a: bool(a.strip())),
    ("local-fact", "what is the default gateway on this machine?", lambda a: "Default gateway:" in a),
    ("advice", "what should I verify first when nginx returns 502 for a local app?", lambda a: "upstream" in a.casefold() or "listen" in a.casefold() or "log" in a.casefold()),
    ("memory-remember", "remember that my core switch uplink is port 1/1/48", lambda a: bool(a.strip())),
    ("memory-recall", "what do you remember about my core switch uplink?", lambda a: "1/1/48" in a),
    ("closing", "thanks", lambda a: bool(a.strip())),
]
CODING = [
    ("code-propose", "add a function named ping(x) that returns x to calc.py", lambda a: "Proposed changes" in a or "did not change" in a),
    ("code-approve", "/approve", lambda a: "Verification" in a or "no pending" in a),
    ("code-undo", "/undo", lambda a: "Undo" in a or "nothing to undo" in a),
]


def stream_chat(url, token, session, message, timeout=600):
    req = urllib.request.Request(
        url + "/v1/chat", data=json.dumps({"session": session, "message": message}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
    records = []
    started = time.monotonic()
    first = None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            if first is None:
                first = time.monotonic() - started
            records.append(json.loads(line))
    return records, time.monotonic() - started, first


def health(url):
    try:
        with urllib.request.urlopen(url + "/healthz", timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "unreachable", "error": str(exc)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8420")
    parser.add_argument("--token", required=True)
    parser.add_argument("--sessions", type=int, default=3)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--workspace", action="store_true", help="include coding commands (service must run with --workspace)")
    args = parser.parse_args(argv)

    script = CONVERSATION + (CODING if args.workspace else [])
    rows = []
    done_windows = []  # (start, end) of each streamed turn to check serialisation
    lock = threading.Lock()
    health_samples = [health(args.url)]
    if health_samples[0].get("status") not in {"ok", "degraded"}:
        print(f"service unreachable at {args.url}: {health_samples[0]}")
        return 2
    print("=" * 78)
    print(f"RazaAI service stress  url={args.url} host={socket.gethostname()} sessions={args.sessions} rounds={args.rounds} workspace={args.workspace}")
    print(f"service: {health_samples[0].get('version')} {health_samples[0].get('status')} model={health_samples[0].get('model')}")
    print("=" * 78)

    def worker(idx):
        sid = f"stress-{idx}-{int(time.time())}"
        for r in range(1, args.rounds + 1):
            for kind, message, ok in script:
                row = {"session": sid, "round": r, "kind": kind, "message": message[:50], "seconds": None, "first_byte": None,
                       "done": 0, "errors": 0, "violations": [], "answer": ""}
                t0 = time.monotonic()
                try:
                    records, seconds, first = stream_chat(args.url, args.token, sid, message)
                except Exception as exc:  # noqa: BLE001
                    row["violations"].append(f"request failed: {type(exc).__name__}: {str(exc)[:80]}")
                    with lock:
                        rows.append(row)
                    continue
                t1 = time.monotonic()
                row["seconds"], row["first_byte"] = round(seconds, 2), round(first or 0, 2)
                dones = [x for x in records if x.get("done")]
                errs = [x for x in records if "error" in x]
                row["done"], row["errors"] = len(dones), len(errs)
                if len(dones) + len(errs) != 1:
                    row["violations"].append(f"stream ended with {len(dones)} done / {len(errs)} error records")
                if dones and dones[0].get("session") != sid:
                    row["violations"].append("done record carries another session id")
                answer = dones[0].get("content", "") if dones else (errs[0].get("error", "") if errs else "")
                row["answer"] = answer.replace("\n", " ")[:120]
                if dones and not ok(answer):
                    row["violations"].append(f"{kind}: unexpected answer")
                with lock:
                    rows.append(row)
                    # The model turn ran between first byte and end; windows must not overlap
                    done_windows.append((t0 + (first or 0), t1, sid))
                    health_samples.append(health(args.url))

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(args.sessions)]
    started = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = time.monotonic() - started

    # Serialisation check: generation windows of different sessions must not interleave
    overlaps = 0
    windows = sorted(done_windows)
    for (s1, e1, a), (s2, e2, b) in zip(windows, windows[1:]):
        if a != b and s2 < e1 - 0.05:
            overlaps += 1
    secs = sorted(r["seconds"] for r in rows if r["seconds"] is not None)
    p50 = secs[len(secs) // 2] if secs else 0
    p95 = secs[int(len(secs) * 0.95)] if secs else 0
    violations = sum(1 for r in rows if r["violations"])
    bad_health = [h for h in health_samples if h.get("status") not in {"ok"}]
    avail = [h.get("memory", {}).get("available_mb") for h in health_samples if h.get("memory")]
    swap = [h.get("memory", {}).get("swap_used_mb") for h in health_samples if h.get("memory")]

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    csv_path = RESULTS / f"service-{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        fields = ["session", "round", "kind", "message", "seconds", "first_byte", "done", "errors", "violations", "answer"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({**r, "violations": "; ".join(r["violations"])})
    md = [f"# Service stress — {stamp}", "",
          f"- url {args.url}, sessions {args.sessions}, rounds {args.rounds}, workspace {args.workspace}",
          f"- requests {len(rows)}, **violations {violations}**, overlapping generations {overlaps} (must be 0), total {total:.0f}s",
          f"- latency p50 {p50:.1f}s p95 {p95:.1f}s (includes queue wait behind other sessions)",
          f"- health samples {len(health_samples)}, non-ok {len(bad_health)}; available MB min {min(a for a in avail if a is not None) if any(a is not None for a in avail) else '?'}; swap MB max {max(s for s in swap if s is not None) if any(s is not None for s in swap) else '?'}",
          "", "| session | round | kind | s | first byte | violations |", "|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['session']} | {r['round']} | {r['kind']} | {r['seconds']} | {r['first_byte']} | {'; '.join(r['violations'])} |")
    md_path = csv_path.with_suffix(".md")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("=" * 78)
    print(f"requests {len(rows)}  violations {violations}  overlaps {overlaps}  p50 {p50:.1f}s  p95 {p95:.1f}s  total {total:.0f}s  non-ok health {len(bad_health)}")
    for r in rows:
        if r["violations"]:
            print(f"  ! {r['session']} r{r['round']} {r['kind']}: {'; '.join(r['violations'])}")
    print(f"CSV:      {csv_path}\nMarkdown: {md_path}")
    print("=" * 78)
    return 0 if violations == 0 and overlaps == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
