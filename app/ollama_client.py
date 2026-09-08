import json
import os
import time
import urllib.request
import urllib.error
import re

from .config import (
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_NUM_BATCH,
    PROFILE,
    OLLAMA_KEEP_ALIVE,
)


class OllamaError(Exception):
    """Raised when communication with Ollama fails."""

    def __init__(
        self,
        message,
        *,
        http_code=None,
        context_exceeded=False,
        n_prompt_tokens=None,
        n_ctx=None,
    ):
        super().__init__(message)
        self.http_code = http_code
        self.context_exceeded = bool(context_exceeded)
        self.n_prompt_tokens = n_prompt_tokens
        self.n_ctx = n_ctx


def _ollama_http_error(exc):
    """Convert Ollama's sometimes double-encoded error body into OllamaError."""
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""

    detail = {}
    try:
        outer = json.loads(body)
        raw = outer.get("error")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {"message": raw}
        if isinstance(raw, dict) and isinstance(raw.get("error"), dict):
            detail = raw["error"]
        elif isinstance(raw, dict):
            detail = raw
    except (json.JSONDecodeError, AttributeError):
        detail = {}

    message = str(detail.get("message") or "")
    context_exceeded = (
        str(detail.get("type") or "") == "exceed_context_size_error"
        or "exceeds the available context size" in message.lower()
    )

    return OllamaError(
        f"Ollama HTTP {exc.code}: {body or exc.reason}",
        http_code=exc.code,
        context_exceeded=context_exceeded,
        n_prompt_tokens=detail.get("n_prompt_tokens"),
        n_ctx=detail.get("n_ctx"),
    )


def normalize_keep_alive(value):
    """Ollama accepts keep_alive as a JSON number (seconds; -1 = forever, 0 = unload) or a Go duration string ("30m", "-1m")."""
    if value is None:
        return "30m"
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return "30m"
    try:
        return int(text)
    except ValueError:
        return text


class OllamaClient:
    def __init__(
        self,
        host: str = OLLAMA_HOST,
        model: str = OLLAMA_MODEL,
        num_ctx: int | None = OLLAMA_NUM_CTX,
        keep_alive: str = OLLAMA_KEEP_ALIVE,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.num_ctx = int(num_ctx) if num_ctx is not None else None
        self.keep_alive = normalize_keep_alive(keep_alive)
        self.last_usage = {
            "prompt_tokens": None,
            "output_tokens": None,
            "context_window": self.num_ctx,
        }
        # Reasoning text from the most recent request (native
        # message.thinking or inline <think>), kept for diagnostics.
        self.last_thinking = ""

    # "think" is only valid for models that advertise the capability
    # (Qwen3 does; Qwen2.5-Coder does not and Ollama rejects the field).
    _capabilities_cache = {}
    _model_info_cache = {}
    # Metadata goes stale when the operator rebuilds a model with
    # `ollama create`; a forever-cache defeats the quantization authority gate.
    _MODEL_INFO_TTL_SECONDS = float(os.getenv("RAZAAI_MODEL_INFO_TTL", "300"))

    def model_info(self, model=None, timeout=5, *, refresh=False):
        """Return Ollama /api/show metadata without loading model weights."""
        tag = str(model or self.model)
        key = (self.host, tag)
        now = time.monotonic()
        if not refresh:
            cached = self._model_info_cache.get(key)
            if cached and now - cached[0] < self._MODEL_INFO_TTL_SECONDS:
                return cached[1]
        request = urllib.request.Request(
            f"{self.host}/api/show",
            data=json.dumps({"model": tag}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                info = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _ollama_http_error(exc) from exc
        except urllib.error.URLError as exc:
            raise OllamaError(f"Unable to connect to Ollama at {self.host}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned invalid model metadata JSON.") from exc
        if not isinstance(info, dict):
            raise OllamaError(f"Ollama returned invalid metadata for {tag}.")
        self._model_info_cache[key] = (now, info)
        return info

    def model_quantization(self, model=None, timeout=5, *, refresh=False):
        info = self.model_info(model=model, timeout=timeout, refresh=refresh)
        details = info.get("details") or {}
        value = details.get("quantization_level") or details.get("quantization")
        if value:
            return str(value).strip()
        # Compatibility with older Ollama outputs/fakes that expose details in
        # free-form text. Unknown is allowed; a known mismatch is not.
        text = str(info.get("model_info") or "")
        match = re.search(r"quantization(?:_level)?[\s:=]+([A-Za-z0-9_]+)", text, re.I)
        return match.group(1) if match else None

    def validate_model_quantization(self, model, expected, timeout=5):
        actual = self.model_quantization(model=model, timeout=timeout)
        if expected and actual and actual.casefold() != str(expected).casefold():
            # Re-read live metadata before refusing, so a stale cache
            # can never false-reject a correctly rebuilt model.
            actual = self.model_quantization(model=model, timeout=timeout, refresh=True) or actual
        if expected and actual and actual.casefold() != str(expected).casefold():
            raise OllamaError(
                f"Refusing to load {model}: quantization is {actual}, expected {expected}. "
                f"Rebuild it with: {PROFILE.model} models"
            )
        return actual

    def validate_memory_budget(self):
        """Reject oversized or unquantized models before loading an 8 GB device."""
        if PROFILE.name != "8g":
            return
        info = self.model_info(refresh=True)
        details = info.get("details") or {}
        count = (info.get("model_info") or {}).get("general.parameter_count")
        if not isinstance(count, (int, float)):
            match = re.fullmatch(r"([0-9.]+)\s*([BM])", str(details.get("parameter_size", "")).upper())
            count = float(match[1]) * (1e9 if match[2] == "B" else 1e6) if match else None
        quant = str(details.get("quantization_level") or "").upper()
        if count is None or count > 4_500_000_000 or not quant.startswith(("Q4", "IQ4")):
            raise OllamaError(
                "The 8g profile requires a model of at most 4.5B parameters in 4-bit quantization. "
                "Run razaai-8g models or choose a compatible local model."
            )

    def loaded_models(self, timeout=5):
        request = urllib.request.Request(f"{self.host}/api/ps", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
            return set()
        return {str(item.get("name") or "") for item in data.get("models", []) if item.get("name")}

    def unload_model(self, model=None, timeout=60):
        """Explicitly unload a resident model before a Jetson model swap."""
        tag = str(model or self.model)
        loaded = self.loaded_models(timeout=min(timeout, 5))
        if not loaded or (tag not in loaded and not any(name.startswith(tag + ":") or name == tag for name in loaded)):
            return False
        payload = {"model": tag, "prompt": "", "stream": False, "keep_alive": 0}
        request = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            raise _ollama_http_error(exc) from exc
        except urllib.error.URLError as exc:
            raise OllamaError(f"Unable to unload {tag} from Ollama at {self.host}: {exc}") from exc
        return True

    def switch_model(self, model, *, expected_quantization=None, unload_previous=True):
        """Move this client to another model with a low-memory-safe handoff."""
        target = str(model)
        previous = str(self.model)
        if target == previous:
            if expected_quantization:
                self.validate_model_quantization(target, expected_quantization)
            return self.detect_context_window(fallback=self.last_usage.get("context_window") or 4096)
        if expected_quantization:
            self.validate_model_quantization(target, expected_quantization)
        if unload_previous:
            self.unload_model(previous)
        self.model = target
        self.last_usage = {
            "prompt_tokens": None,
            "output_tokens": None,
            "context_window": self.num_ctx,
        }
        return self.detect_context_window(fallback=4096)

    def capabilities(self, timeout=5):
        cached = self._capabilities_cache.get((self.host, self.model))
        if cached is not None:
            return cached
        caps = set()
        try:
            info = self.model_info(timeout=timeout)
            if not isinstance(info.get("capabilities"), list):
                caps = {"thinking"}
            else:
                caps = {str(c) for c in info["capabilities"]}
        except Exception:  # noqa: BLE001 - a probe must never break a request
            caps = {"thinking"}
        self._capabilities_cache[(self.host, self.model)] = caps
        return caps

    def _think_field(self):
        """Preserve model-default thinking unless the operator selects an override."""
        mode = os.getenv("RAZAAI_THINK", "auto").strip().casefold()
        if mode in {"", "auto"}:
            return {}
        if mode not in {"1", "true", "yes", "on", "0", "false", "no", "off", "low", "medium", "high"}:
            raise ValueError("RAZAAI_THINK must be auto, on, off, low, medium or high")
        if "thinking" not in self.capabilities():
            return {}
        if mode in {"low", "medium", "high"}:
            return {"think": mode}
        return {"think": mode in {"1", "true", "yes", "on"}}

    def detect_context_window(self, fallback=None, timeout=5):
        """Return the effective context window for the active model."""
        if self.num_ctx is not None:
            self.last_usage["context_window"] = self.num_ctx
            return self.num_ctx

        detected = None
        try:
            info = self.model_info(timeout=timeout)
            params = str(info.get("parameters") or "")
            match = re.search(r"^\s*num_ctx\s+(\d+)\s*$", params, flags=re.M)
            if match:
                detected = int(match.group(1))
            if detected is None:
                # Fall back to the architecture's trained context length if the
                # Modelfile does not pin num_ctx (Ollama then defaults to 2048
                # or its own default; be conservative and use that default).
                detected = None
        except (OllamaError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
                ValueError, OSError):
            detected = None

        if detected is None or detected < 1024:
            detected = int(fallback or 4096)
        self.last_usage["context_window"] = detected
        return detected

    def _record_usage(self, result):
        """Record Ollama's authoritative token counters for the TUI."""
        if not isinstance(result, dict):
            return
        prompt = result.get("prompt_eval_count")
        output = result.get("eval_count")
        self.last_usage = {
            "prompt_tokens": int(prompt) if isinstance(prompt, (int, float)) else None,
            "output_tokens": int(output) if isinstance(output, (int, float)) else None,
            "context_window": self.last_usage.get("context_window") or self.num_ctx,
        }

    def chat(self, messages, tools=None, format=None, num_predict=None):
        """Send a conversation to RazaAI."""

        self.validate_memory_budget()
        payload = {
            "model": self.model,
            "messages": messages,
            **self._think_field(),
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"num_batch": OLLAMA_NUM_BATCH},
        }
        if format:
            payload["format"] = format
        if num_predict:
            payload.setdefault("options", {})["num_predict"] = int(num_predict)

        # Only override the model's context when explicitly configured. Leaving
        # options.num_ctx absent allows the active Ollama Modelfile to select a
        # hardware-appropriate value.
        if self.num_ctx is not None:
            payload.setdefault("options", {})["num_ctx"] = self.num_ctx

        if tools:
            payload["tools"] = tools

        data = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=data,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                result = json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as exc:
            raise _ollama_http_error(exc) from exc

        except urllib.error.URLError as exc:

            raise OllamaError(
                f"Unable to connect to Ollama " f"at {self.host}: {exc}"
            ) from exc

        except json.JSONDecodeError as exc:

            raise OllamaError("Ollama returned invalid JSON.") from exc

        message = result.get("message") or {}
        # Capture native reasoning for diagnostics before stripping.
        reasoning = message.get("thinking")
        if isinstance(reasoning, str) and reasoning:
            self.last_thinking = reasoning[-8000:]
        content = message.get("content")
        if isinstance(content, str):
            if "</think>" in content:
                # Keep the reasoning for diagnostics, then answer-only content.
                self.last_thinking = (
                    content.rsplit("</think>", 1)[0].replace("<think>", "", 1)[-8000:]
                    or self.last_thinking
                )
                content = content.rsplit("</think>", 1)[1]
            content = re.sub(
                r"<think>.*?</think>",
                "",
                content,
                flags=re.I | re.S,
            ).strip()
            message["content"] = content
            result["message"] = message

        self._record_usage(result)
        return result


    # Streaming-safe <think> separation. Reasoning text must never
    # reach on_chunk: the UI shows an animation for thinking, and the final
    # answer must not flash raw reasoning into the chat first.
    _THINK_OPEN = "<think>"
    _THINK_CLOSE = "</think>"

    @classmethod
    def _split_think_stream(cls, state, pending_holder, chunk):
        """Yield (kind, text) pieces for one streamed chunk."""
        text = pending_holder[0] + str(chunk or "")
        pending_holder[0] = ""
        while text:
            marker = cls._THINK_CLOSE if state[0] == "inside" else cls._THINK_OPEN
            idx = text.find(marker)
            if idx >= 0:
                head, text = text[:idx], text[idx + len(marker):]
                if head:
                    yield ("think" if state[0] == "inside" else "body"), head
                state[0] = "outside" if marker == cls._THINK_CLOSE else "inside"
                continue
            # No full marker: emit everything except a possible partial one.
            keep = 0
            for size in range(1, len(marker)):
                if text.endswith(marker[:size]):
                    keep = size
            body, pending = text[: len(text) - keep], text[len(text) - keep:]
            if body:
                yield ("think" if state[0] == "inside" else "body"), body
            pending_holder[0] = pending
            break

    def chat_stream(self, messages, tools=None, on_chunk=None, on_thinking=None):
        """Stream assistant text from Ollama and return a normal final result."""
        self.validate_memory_budget()
        payload = {
            "model": self.model,
            "messages": messages,
            **self._think_field(),
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {"num_batch": OLLAMA_NUM_BATCH},
        }
        if self.num_ctx is not None:
            payload["options"]["num_ctx"] = self.num_ctx
        if tools:
            payload["tools"] = tools

        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        chunks = []
        thinking_chunks = []
        final_message = {"role": "assistant", "content": ""}
        final_event = {}
        think_state = ["outside"]
        think_pending = [""]
        # Socket timeouts bound a single stuck read, not the request.
        # A dribbling stream could otherwise hold the server's turn lock for
        # as long as it keeps emitting bytes. Wall-clock bound the whole read.
        stream_deadline = float(os.getenv("RAZAAI_OLLAMA_STREAM_DEADLINE", "600"))
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                for raw_line in response:
                    if time.monotonic() - started > stream_deadline:
                        raise OllamaError(
                            f"Ollama stream exceeded {stream_deadline:.0f}s wall-clock; abandoning the turn."
                        )
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    event = json.loads(line)
                    if event.get("error"):
                        raise OllamaError(str(event["error"]))
                    message = event.get("message") or {}
                    # Current Ollama delivers native reasoning in a separate
                    # message.thinking field; route it away from the answer.
                    reasoning = message.get("thinking") or ""
                    if reasoning:
                        thinking_chunks.append(reasoning)
                        if on_thinking is not None:
                            on_thinking(reasoning)
                    content = message.get("content") or ""
                    if content:
                        for kind, piece in self._split_think_stream(
                            think_state, think_pending, content
                        ):
                            if kind == "think":
                                thinking_chunks.append(piece)
                                if on_thinking is not None:
                                    on_thinking(piece)
                            else:
                                chunks.append(piece)
                                if on_chunk is not None:
                                    on_chunk(piece)
                    if message.get("tool_calls"):
                        final_message["tool_calls"] = message["tool_calls"]
                    if event.get("done"):
                        final_event = event
                        break
        except urllib.error.HTTPError as exc:
            raise _ollama_http_error(exc) from exc
        except urllib.error.URLError as exc:
            raise OllamaError(
                f"Unable to connect to Ollama at {self.host}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned invalid streaming JSON.") from exc

        if not final_event:
            raise OllamaError("Ollama stream ended before the answer completed. Retry the request.")
        if think_pending[0] and think_state[0] == "outside":
            chunks.append(think_pending[0])
            if on_chunk is not None:
                on_chunk(think_pending[0])
        self.last_thinking = "".join(thinking_chunks)[-8000:]
        # Thinking never entered `chunks`; the strip is belt-and-braces for
        # models that emit stray markers without blocks.
        content = "".join(chunks)
        content = re.sub(r"</?think>", "", content, flags=re.I).strip()
        final_message["content"] = content
        result = dict(final_event or {})
        result["message"] = final_message
        result["done"] = True
        self._record_usage(result)
        return result
