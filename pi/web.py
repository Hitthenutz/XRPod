"""
XRPod web server: serves the HUD and its JSON API from the Pi.

API (all JSON):
  GET   /api/settings          current settings
  PATCH /api/settings          change some settings, e.g. {"fan_speed_pct": 40}
  GET   /api/readings/latest   newest sensor reading (or null)
  GET   /api/history?limit=50  newest settings changes first
  GET   /api/events            Server-Sent Events stream: "settings",
                               "reading" and "history" events, live

Everything else serves the built HUD from ../hud/dist (run `npm run build` in hud/).

Security: this is meant for the pod's local network. Anyone who can reach
the Pi can use the HUD; there is no login. Writes are
protected against other websites (CSRF): they must be JSON, and a browser's
Origin header must match the Pi's own address.
"""

import json
import logging
import mimetypes
import os
import queue
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from store import ValidationError

log = logging.getLogger("xrpod.web")

MAX_BODY_BYTES = 4096
SSE_HEARTBEAT_SECONDS = 15

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")


class EventHub:
    """Fans server events out to every connected HUD."""

    def __init__(self):
        self._lock = threading.Lock()
        self._clients = set()

    def subscribe(self):
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._clients.add(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            self._clients.discard(q)

    def publish(self, event, data):
        message = f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(message)
            except queue.Full:
                # A client that stopped reading: drop it (it will reconnect)
                # and wake its thread so it exits. Never block the publisher.
                self.unsubscribe(q)
                try:
                    q.get_nowait()
                    q.put_nowait(None)
                except (queue.Empty, queue.Full):
                    pass


class Handler(BaseHTTPRequestHandler):
    """Routes requests. Shared state lives on the server: pod_store, pod_hub,
    pod_static_root and pod_on_settings_changed (see start_server)."""

    server_version = "XRPod"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    # ------------------------------------------------------------ helpers
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, message):
        self._send_json(status, {"error": message})

    def _same_origin(self):
        """Block writes from other websites. Non-browser clients (Unity,
        curl) send no Origin header and are allowed."""
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        return urlsplit(origin).netloc == self.headers.get("Host")

    # ------------------------------------------------------------- routes
    def do_GET(self):  # noqa: N802 - http.server naming
        url = urlsplit(self.path)
        if url.path == "/api/settings":
            return self._send_json(HTTPStatus.OK, self.server.pod_store.get_settings())
        if url.path == "/api/readings/latest":
            return self._send_json(HTTPStatus.OK, self.server.pod_store.get_latest_reading())
        if url.path == "/api/history":
            try:
                limit = int(parse_qs(url.query).get("limit", ["50"])[0])
            except ValueError:
                return self._error(HTTPStatus.BAD_REQUEST, "limit must be a number")
            return self._send_json(HTTPStatus.OK, self.server.pod_store.get_history(limit))
        if url.path == "/api/events":
            return self._stream_events()
        if url.path.startswith("/api/"):
            return self._error(HTTPStatus.NOT_FOUND, "no such endpoint")
        return self._serve_static(url.path)

    def do_PATCH(self):  # noqa: N802
        if urlsplit(self.path).path != "/api/settings":
            return self._error(HTTPStatus.NOT_FOUND, "no such endpoint")
        if not self._same_origin():
            return self._error(HTTPStatus.FORBIDDEN, "cross-origin request blocked")
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "send JSON")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY_BYTES:
            return self._error(HTTPStatus.BAD_REQUEST, "body missing or too large")
        try:
            patch = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            return self._error(HTTPStatus.BAD_REQUEST, "body must be JSON")

        try:
            settings, rows = self.server.pod_store.update_settings(patch, changed_by=self.client_address[0])
        except ValidationError as err:
            return self._error(HTTPStatus.BAD_REQUEST, str(err))

        if rows:
            self.server.pod_hub.publish("settings", settings)
            self.server.pod_hub.publish("history", rows)
            self.server.pod_on_settings_changed()
        return self._send_json(HTTPStatus.OK, settings)

    def do_POST(self):  # noqa: N802
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "use PATCH /api/settings")

    do_PUT = do_DELETE = do_POST  # noqa: N815

    # --------------------------------------------------------------- SSE
    def _stream_events(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = self.server.pod_hub.subscribe()
        try:
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            while True:
                try:
                    message = q.get(timeout=SSE_HEARTBEAT_SECONDS)
                except queue.Empty:
                    message = b": keep-alive\n\n"
                if message is None:
                    break
                self.wfile.write(message)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # HUD closed or lost Wi-Fi
        finally:
            self.server.pod_hub.unsubscribe(q)
            self.close_connection = True

    # ------------------------------------------------------------ static
    def _serve_static(self, path):
        target = (self.server.pod_static_root / path.lstrip("/")).resolve()
        # Refuse anything outside dist/ (e.g. /../pi/xrpod.db).
        if self.server.pod_static_root not in target.parents and target != self.server.pod_static_root:
            return self._error(HTTPStatus.NOT_FOUND, "not found")
        if not target.is_file():
            # Single-page app: unknown paths get the HUD itself.
            target = self.server.pod_static_root / "index.html"
            if not target.is_file():
                return self._error(
                    HTTPStatus.NOT_FOUND, "HUD not built yet: run `npm run build`"
                )
        body = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # Vite fingerprints files in assets/, so they can be cached forever.
        if target.parent.name == "assets":
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def start_server(store, hub, host, port, static_dir, on_settings_changed=lambda: None):
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.pod_store = store
    server.pod_hub = hub
    server.pod_static_root = Path(static_dir).resolve()
    server.pod_on_settings_changed = on_settings_changed
    thread = threading.Thread(target=server.serve_forever, name="web", daemon=True)
    thread.start()
    log.info("HUD at http://%s:%s (static files from %s)", host, port, os.path.abspath(static_dir))
    return server
