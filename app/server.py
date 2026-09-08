"""RazaAI service mode."""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
import urllib.request
from collections import OrderedDict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import (APP_NAME, APP_VERSION, OLLAMA_HOST, OLLAMA_MODEL, SELFOPS_ENABLED,
                     PROFILE, OLLAMA_NUM_CTX, OLLAMA_NUM_BATCH, OLLAMA_KEEP_ALIVE, positive_int)
from .ollama_client import normalize_keep_alive
from .runtime_health import memory_snapshot

DEFAULT_HOST = os.getenv("RAZAAI_SERVER_HOST", "127.0.0.1")
DEFAULT_PORT = positive_int("RAZAAI_SERVER_PORT", PROFILE.port)
MAX_SESSIONS = positive_int("RAZAAI_SERVER_MAX_SESSIONS", PROFILE.sessions)
SESSION_IDLE_SECONDS = int(os.getenv("RAZAAI_SERVER_SESSION_IDLE", "3600"))
# Bound the wait for another session to finish its turn.
TURN_QUEUE_TIMEOUT = float(os.getenv("RAZAAI_TURN_QUEUE_TIMEOUT", "1800"))
MAX_MESSAGE_CHARS = 12000
TOKEN_FILE = Path(os.getenv("RAZAAI_SERVER_TOKEN_FILE", "")).expanduser() if os.getenv("RAZAAI_SERVER_TOKEN_FILE") else None
WEB_DIR = Path(__file__).resolve().parent / "web"


def resolve_token() -> str:
    """Read the configured bearer token or create a private token file."""
    env = os.getenv("RAZAAI_SERVER_TOKEN", "").strip()
    if env:
        if env.casefold() in {"change-me", "changeme", "password"}:
            raise ValueError("Set a unique RAZAAI_SERVER_TOKEN or use a generated token file")
        return env
    if TOKEN_FILE and TOKEN_FILE.is_file():
        value = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(24)
    if TOKEN_FILE:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise ValueError("Token file is empty or changed during startup") from None
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value + "\n")
    return value


def ollama_status(host: str = OLLAMA_HOST, model: str = OLLAMA_MODEL, timeout: float = 2.0) -> dict:
    """Read-only probe: is Ollama up, is the model present, is it loaded."""
    status = {"reachable": False, "model_present": False, "model_loaded": False, "error": None}
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
        status["reachable"] = True
        names = {m.get("name") for m in tags.get("models", [])}
        status["model_present"] = model in names or model + ":latest" in names
    except Exception as exc:  # noqa: BLE001 - health probes must not raise
        status["error"] = f"tags: {exc}"
        return status
    try:
        with urllib.request.urlopen(f"{host}/api/ps", timeout=timeout) as resp:
            ps = json.loads(resp.read().decode("utf-8"))
        status["model_loaded"] = any(
            str(m.get("name", "")) in {model, model + ":latest"}
            for m in ps.get("models", [])
        )
    except Exception as exc:  # noqa: BLE001
        status["error"] = f"ps: {exc}"
    return status


def warm_model(host: str = OLLAMA_HOST, model: str = OLLAMA_MODEL, keep_alive: str = OLLAMA_KEEP_ALIVE, timeout: float = 300.0) -> dict:
    """Warm the model and report load errors without stopping the listener."""
    payload = json.dumps({"model": model, "prompt": "", "keep_alive": normalize_keep_alive(keep_alive), "stream": False, "options": {"num_ctx": OLLAMA_NUM_CTX, "num_batch": OLLAMA_NUM_BATCH}}).encode("utf-8")
    req = urllib.request.Request(f"{host}/api/generate", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    started = time.monotonic()
    try:
        if PROFILE.name == "8g":
            from .ollama_client import OllamaClient
            OllamaClient(host=host, model=model).validate_memory_budget()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return {"loaded": True, "seconds": round(time.monotonic() - started, 1), "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"loaded": False, "seconds": round(time.monotonic() - started, 1), "error": str(exc)}


class SessionPool:
    """Bounded, idle-evicting pool of RazaAgent instances."""

    def __init__(self, agent_factory, max_sessions=MAX_SESSIONS, idle_seconds=SESSION_IDLE_SECONDS):
        self._factory = agent_factory
        self._max = max(1, int(max_sessions))
        self._idle = max(60, int(idle_seconds))
        self._sessions: "OrderedDict[str, dict]" = OrderedDict()
        self._lock = threading.Lock()

    def _evict_locked(self):
        now = time.monotonic()
        for sid in [s for s, e in self._sessions.items()
                    if not e.get("busy") and now - e["last_used"] > self._idle]:
            self._sessions.pop(sid, None)
        while len(self._sessions) > self._max:
            victim = next((s for s, e in self._sessions.items() if not e.get("busy")), None)
            if victim is None:
                break  # Every session has a turn in flight; over-limit is safer than eviction
            self._sessions.pop(victim, None)

    def get(self, session_id: str, *, reserve=False):
        with self._lock:
            self._evict_locked()
            entry = self._sessions.get(session_id)
            if entry is None:
                entry = {"agent": None, "created": time.time(), "last_used": time.monotonic(), "turns": 0}
                self._sessions[session_id] = entry
                self._evict_locked()
            if reserve:
                entry["busy"] = True
            entry["last_used"] = time.monotonic()
            self._sessions.move_to_end(session_id)
            return entry

    def release(self, session_id: str):
        """Keep a completed or failed session available until its idle timeout."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry:
                entry["busy"] = False
                entry["last_used"] = time.monotonic()

    def note_turn(self, session_id: str):
        """Count a completed turn under the pool lock (no torn counters)."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is not None:
                entry["turns"] += 1

    def new_agent(self):
        """Construct a fresh agent via the factory (never called under the pool lock)."""
        return self._factory()

    def drop(self, session_id: str) -> bool:
        with self._lock:
            if self._sessions.get(session_id, {}).get("busy"):
                return False
            return self._sessions.pop(session_id, None) is not None

    def describe(self) -> list[dict]:
        with self._lock:
            self._evict_locked()
            return [
                {"id": sid, "turns": e["turns"], "created": e["created"],
                 "idle_seconds": round(time.monotonic() - e["last_used"], 1)}
                for sid, e in self._sessions.items()
            ]


class RazaService:
    """Everything the HTTP handler needs, independent of HTTP."""

    def __init__(self, agent_factory=None, token: str | None = None, workspace_root=None):
        if agent_factory is None:
            from .agent import RazaAgent

            def agent_factory():
                return RazaAgent(workspace_root=workspace_root)

        self.pool = SessionPool(agent_factory)
        self.token = token if token is not None else resolve_token()
        self.turn_lock = threading.Lock()  # One Ollama slot -> one turn at a time
        self._stats_lock = threading.Lock()
        self.started = time.time()
        self.turns = 0
        self.workspace_root = str(workspace_root) if workspace_root else None
        self.warmup = {"requested": False, "loaded": False, "seconds": None, "error": None}

    def warm_in_background(self):
        """Kick the model load off without blocking the listener."""
        self.warmup["requested"] = True

        def _run():
            if not self.turn_lock.acquire(timeout=TURN_QUEUE_TIMEOUT):
                self.warmup.update({"loaded": False, "seconds": None, "error": "gave up waiting for turn lock"})
                return
            try:
                result = warm_model(keep_alive=OLLAMA_KEEP_ALIVE)
                self.warmup.update(result)
                print(f"[Warmup] model {'loaded' if result['loaded'] else 'NOT loaded'} in {result['seconds']}s"
                      + (f": {result['error']}" if result["error"] else ""))
            finally:
                self.turn_lock.release()

        threading.Thread(target=_run, name="razaai-warmup", daemon=True).start()

    def health(self) -> dict:
        ollama = ollama_status()
        mem = memory_snapshot()
        degraded = []
        if not ollama["reachable"]:
            degraded.append("ollama unreachable")
        elif not ollama["model_present"]:
            degraded.append(f"model {OLLAMA_MODEL} not present")
        degraded.extend(mem.get("warnings", []))
        return {
            "app": APP_NAME,
            "version": APP_VERSION,
            "status": "degraded" if degraded else "ok",
            "degraded": degraded,
            "uptime_seconds": round(time.time() - self.started, 1),
            "turns_served": self.turns,
            "model": OLLAMA_MODEL,
            "ollama": ollama,
            "memory": {k: mem.get(k) for k in ("available_mb", "swap_used_mb", "model_process", "model_rss_mb")},
            "selfops_enabled": SELFOPS_ENABLED,
            "warmup": self.warmup,
            "profile": PROFILE.name,
            "context_window": OLLAMA_NUM_CTX,
            "sessions": len(self.pool.describe()),
        }

    def chat(self, session_id: str, message: str, emit):
        """Run one turn; `emit(record)` receives NDJSON records in order."""
        if not message or len(message) > MAX_MESSAGE_CHARS:
            emit({"error": f"message must be 1-{MAX_MESSAGE_CHARS} characters"})
            return
        started = time.monotonic()
        if not self.turn_lock.acquire(timeout=TURN_QUEUE_TIMEOUT):
            emit({"error": "busy: another turn holds the model. Retry shortly."})
            return
        try:
            entry = self.pool.get(session_id, reserve=True)
            agent = entry["agent"]
            if agent is None:
                agent = self.pool.new_agent()
                entry["agent"] = agent

            def on_stream(chunk):
                if chunk:
                    emit({"delta": chunk})

            def on_thinking(chunk):
                if chunk:
                    emit({"thinking_delta": chunk})

            import inspect

            ask_kwargs = {"on_stream": on_stream}
            if "on_thinking" in inspect.signature(agent.ask).parameters:
                ask_kwargs["on_thinking"] = on_thinking
            content = agent.ask(message, **ask_kwargs)
            self.pool.note_turn(session_id)
            with self._stats_lock:
                self.turns += 1
            usage = getattr(getattr(agent, "client", None), "last_usage", {}) or {}
            emit({
                "done": True, "content": content, "session": session_id,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "prompt_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "context_window": getattr(agent, "context_window", None),
            })
        except _ClientGone:
            raise
        except Exception as exc:
            emit({"error": f"{type(exc).__name__}: {exc}"})
        finally:
            self.pool.release(session_id)
            self.turn_lock.release()


def make_handler(service: RazaService):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"RazaAI/{APP_VERSION}"

        # Streaming responses use HTTP/1.1 chunk framing.
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def end_headers(self):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            super().end_headers()

        def _json(self, code, payload):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorised(self) -> bool:
            header = self.headers.get("Authorization", "")

            # Accept bearer credentials only through the Authorization header.
            return header.startswith("Bearer ") and secrets.compare_digest(header[7:].strip().encode("utf-8"), service.token.encode("utf-8"))

        def _deny(self):
            self._drain_body()
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "missing or invalid bearer token"})

        def _read_json(self):
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
                self.close_connection = True
                return None
            try:
                length = int(lengths[0])
            except ValueError:
                self.close_connection = True
                return None
            if length <= 0 or length > 1_000_000:
                self.close_connection = True
                return None
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError, OSError):
                self.close_connection = True
                return None

        def _drain_body(self, limit=None):
            """Close rejected requests so unread bytes cannot become another request."""
            self.close_connection = True

        def log_message(self, fmt, *args):  # Quiet by default; journald has enough
            if os.getenv("RAZAAI_SERVER_DEBUG") == "1":
                super().log_message(fmt, *args)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/healthz":
                health = service.health()
                self._json(HTTPStatus.OK if health["status"] == "ok" else HTTPStatus.SERVICE_UNAVAILABLE, health)
                return
            if path in ("/", "/index.html"):
                page = WEB_DIR / "index.html"
                if not page.is_file():
                    self._json(HTTPStatus.NOT_FOUND, {"error": "web client not bundled"})
                    return
                data = page.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if not self._authorised():
                self._deny()
                return
            if path == "/v1/sessions":
                self._json(HTTPStatus.OK, {"sessions": service.pool.describe()})
                return
            if path == "/v1/doctor":
                from .doctor import checks, render
                results = checks()
                text, code = render(results)
                self._json(HTTPStatus.OK, {"checks": results, "text": text, "exit_code": code})
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "unknown route"})

        def do_DELETE(self):
            path = self.path.split("?", 1)[0]
            if not self._authorised():
                self._deny()
                return
            if path.startswith("/v1/sessions/"):
                sid = path.rsplit("/", 1)[-1]
                self._json(HTTPStatus.OK, {"dropped": service.pool.drop(sid), "session": sid})
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "unknown route"})

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if not self._authorised():
                self._deny()
                return
            if path != "/v1/chat":
                self.close_connection = True
                self._json(HTTPStatus.NOT_FOUND, {"error": "unknown route"})
                return
            body = self._read_json()
            if not isinstance(body, dict) or not isinstance(body.get("message"), str):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "expected JSON {\"session\": str, \"message\": str}"})
                return
            session_id = body.get("session") or "default"
            if not isinstance(session_id, str) or len(session_id) > 64:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "session must be a string of at most 64 characters"})
                return
            message = body["message"].strip()

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def emit(record):
                line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
                try:
                    self.wfile.write(f"{len(line):X}\r\n".encode("ascii") + line + b"\r\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    raise _ClientGone()

            try:
                service.chat(session_id, message, emit)
            except _ClientGone:
                return
            try:
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


class _ClientGone(Exception):
    pass


class BoundedHTTPServer(ThreadingHTTPServer):
    """Bound client threads, including connections waiting for request headers."""

    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self._slots = threading.BoundedSemaphore(16)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def serve(host=DEFAULT_HOST, port=DEFAULT_PORT, workspace_root=None, token=None):
    if PROFILE.name != "standard":
        raise ValueError("The browser is available only in razaai. Run razaai-8g for the Jetson terminal interface.")
    service = RazaService(workspace_root=workspace_root, token=token)
    httpd = BoundedHTTPServer((host, port), make_handler(service))
    httpd.daemon_threads = True
    print(f"{APP_NAME} v{APP_VERSION} service on http://{host}:{port}  model={OLLAMA_MODEL}")
    if os.getenv("RAZAAI_SERVER_WARMUP", "1").strip().casefold() not in {"0", "false", "no", "off"}:
        service.warm_in_background()
    if os.getenv("RAZAAI_SERVER_TOKEN", "").strip() or (TOKEN_FILE and TOKEN_FILE.is_file()):
        print("Bearer token: (from environment/token file)")
    else:
        print(f"Bearer token: {service.token}   (set RAZAAI_SERVER_TOKEN or RAZAAI_SERVER_TOKEN_FILE to persist)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="RazaAI service mode")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--workspace", default=None, help="optional coding workspace for raza-code over the API")
    args = parser.parse_args(argv)
    serve(args.host, args.port, workspace_root=args.workspace)


if __name__ == "__main__":
    main()
