"""A small local web server: one page plus a JSON API."""

from __future__ import annotations

import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from macarony.pipeline import DEFAULT_OPTIONS, process, tokenize
from macarony.translate import (
    DEFAULT_LANGUAGES,
    LANGUAGE_NAMES,
    GoogleTranslator,
    OfflineTranslator,
)

WEB_DIR = Path(__file__).with_name("web")
#: Plenty for a sentence; stops a stray large POST from eating memory.
MAX_BODY = 64 * 1024


class MacaronyServer(ThreadingHTTPServer):
    """Holds the shared translators so their caches survive between requests."""

    daemon_threads = True

    def __init__(self, address, handler, force_offline: bool = False) -> None:
        super().__init__(address, handler)
        self.force_offline = force_offline
        self.google = GoogleTranslator()
        self.offline = OfflineTranslator()


class MacaronyHandler(BaseHTTPRequestHandler):
    server_version = "Macarony"
    protocol_version = "HTTP/1.1"

    # --- plumbing ---------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - base class name
        print(f"  {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("request body is too large")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("expected a JSON object")
        return payload

    # --- routes -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - base class name
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                body = (WEB_DIR / "index.html").read_bytes()
            except OSError:
                self._error(500, "index.html is missing from the installation")
                return
            self._send(200, body, "text/html; charset=utf-8")
        elif path == "/api/languages":
            self._send_json({
                "default": list(DEFAULT_LANGUAGES),
                "all": [{"code": code, "name": name} for code, name in LANGUAGE_NAMES.items()],
                "defaults": DEFAULT_OPTIONS,
                "force_offline": self.server.force_offline,
                "offline_words": self.server.offline.words,
            })
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._error(404, f"no route for {path}")

    def do_HEAD(self) -> None:  # noqa: N802 - base class name
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802 - base class name
        path = self.path.split("?", 1)[0]
        try:
            payload = self._read_json()
        except ValueError as exc:
            self._error(400, f"bad request body: {exc}")
            return

        try:
            if path == "/api/tokenize":
                self._send_json({"tokens": tokenize(str(payload.get("sentence") or ""))})
            elif path == "/api/process":
                self._send_json(self._process(payload))
            else:
                self._error(404, f"no route for {path}")
        except Exception as exc:  # a local tool: report the fault, keep serving
            traceback.print_exc()
            self._error(500, f"{type(exc).__name__}: {exc}")

    def _process(self, payload: dict) -> dict:
        options = dict(payload.get("options") or {})
        if self.server.force_offline:
            options["offline"] = True
        translator = self.server.offline if options.get("offline") else self.server.google
        return process(
            str(payload.get("sentence") or ""),
            payload.get("selected") or [],
            options,
            translator=translator,
        )


def serve(host: str = "127.0.0.1", port: int = 8000, force_offline: bool = False) -> MacaronyServer:
    return MacaronyServer((host, port), MacaronyHandler, force_offline=force_offline)
