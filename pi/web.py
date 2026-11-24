"""
XRPod web server: serves the HUD and its JSON API from the Pi.

API (all JSON):
  GET   /api/settings          current settings
  PATCH /api/settings          change some settings, e.g. {"fan_speed_pct": 40}
  GET   /api/readings/latest   newest sensor reading (or null)
  GET   /api/history?limit=50  newest settings changes first
  GET   /api/vr/state          what the headset last reported (or null)
  PUT   /api/vr/state          headset reports its environment and zone
  PUT   /api/vr/frame          headset sends its live view: {"jpeg_base64": "..."}
  GET   /api/vr/frame          the newest live-view picture (image/jpeg), or
                               204 No Content if there's none from the last 3 s
  GET   /api/events          Server-Sent Events stream: "settings",
                               "reading", "history", "vr", "event" (data log)
                               and "session" events, live

Data log (datalog.py):
  GET   /api/log/events?limit=100&level=warning   newest events first
  GET   /api/log/sessions                         recording sessions, newest first
  PUT   /api/log/session   {"action": "start", "name": "Trial 1"} | {"action": "stop"}
                           | {"action": "delete", "id": "3"}
  GET   /api/log/readings.csv?session=3 or ?minutes=60   readings as CSV
  GET   /api/log/events.csv?session=3 or ?minutes=60     events + settings changes as CSV

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
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import datalog
from store import ValidationError
from vr import MAX_FRAME_BODY_BYTES, VrFrame, VrState

log = logging.getLogger("xrpod.web")

MAX_BODY_BYTES = 4096
SSE_HEARTBEAT_SECONDS = 15
# CSV downloads by time cover at most this long (a week).
MAX_EXPORT_MINUTES = 7 * 24 * 60

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
    pod_vr, pod_static_root and pod_on_settings_changed (see start_server)."""

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

    def _read_json_body(self, max_bytes=MAX_BODY_BYTES):
        """Apply the write protections and return the parsed body, or send
        the error and return None. Only the live-view picture may be bigger
        than MAX_BODY_BYTES."""
        if not self._same_origin():
            self._error(HTTPStatus.FORBIDDEN, "cross-origin request blocked")
            return None
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "send JSON")
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= max_bytes:
            self._error(HTTPStatus.BAD_REQUEST, "body missing or too large")
            return None
        try:
            return json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            self._error(HTTPStatus.BAD_REQUEST, "body must be JSON")
            return None

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
        if url.path == "/api/vr/state":
            return self._send_json(HTTPStatus.OK, self.server.pod_vr.latest())
        if url.path == "/api/vr/frame":
            return self._send_frame()
        if url.path == "/api/events":
            return self._stream_events()
        if url.path.startswith("/api/log/"):
            return self._get_log(url)
        if url.path.startswith("/api/"):
            return self._error(HTTPStatus.NOT_FOUND, "no such endpoint")
        return self._serve_static(url.path)

    def do_PATCH(self):  # noqa: N802
        if urlsplit(self.path).path != "/api/settings":
            return self._error(HTTPStatus.NOT_FOUND, "no such endpoint")
        patch = self._read_json_body()
        if patch is None:
            return None

        try:
            settings, rows = self.server.pod_store.update_settings(patch, changed_by=self.client_address[0])
        except ValidationError as err:
            return self._error(HTTPStatus.BAD_REQUEST, str(err))

        if rows:
            self.server.pod_hub.publish("settings", settings)
            self.server.pod_hub.publish("history", rows)
            self.server.pod_on_settings_changed()
        return self._send_json(HTTPStatus.OK, settings)

    def do_PUT(self):  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/api/vr/frame":
            return self._put_frame()
        if path == "/api/log/session":
            return self._put_session()
        if path != "/api/vr/state":
            return self._error(HTTPStatus.METHOD_NOT_ALLOWED, "use PATCH /api/settings")
        msg = self._read_json_body()
        if msg is None:
            return None
        try:
            state, changed = self.server.pod_vr.update(msg)
        except ValidationError as err:
            return self._error(HTTPStatus.BAD_REQUEST, str(err))
        if changed:
            self.server.pod_hub.publish("vr", state)
        return self._send_json(HTTPStatus.OK, state)

    # --------------------------------------------------------- live view
    def _put_frame(self):
        msg = self._read_json_body(MAX_FRAME_BODY_BYTES)
        if msg is None:
            return None
        try:
            self.server.pod_vr_frame.update(msg)
        except ValidationError as err:
            return self._error(HTTPStatus.BAD_REQUEST, str(err))
        # Not published over /api/events: pictures are too big for it. The
        # HUD fetches GET /api/vr/frame a few times a second instead.
        return self._send_json(HTTPStatus.OK, {"ok": True})

    def _send_frame(self):
        image = self.server.pod_vr_frame.latest()
        if image is None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(image)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(image)

    # ---------------------------------------------------------- data log
    def _get_log(self, url):
        store = self.server.pod_store
        query = parse_qs(url.query)
        try:
            if url.path == "/api/log/events":
                limit = int(query.get("limit", ["100"])[0])
                level = query.get("level", ["info"])[0]
                return self._send_json(HTTPStatus.OK, store.get_events(limit, level))
            if url.path == "/api/log/sessions":
                return self._send_json(HTTPStatus.OK, store.get_sessions())
            if url.path in ("/api/log/readings.csv", "/api/log/events.csv"):
                label, start, end = self._export_range(query)
                if url.path.endswith("readings.csv"):
                    body = datalog.readings_csv(store.readings_between(start, end))
                    name = datalog.file_name(label, "readings")
                else:
                    body = datalog.events_csv(store.events_between(start, end))
                    name = datalog.file_name(label, "events")
                return self._send_csv(body, name)
        except ValueError as err:  # ValidationError, or a number that isn't one
            message = str(err) if isinstance(err, ValidationError) else "limit and minutes must be numbers"
            return self._error(HTTPStatus.BAD_REQUEST, message)
        return self._error(HTTPStatus.NOT_FOUND, "no such endpoint")

    def _export_range(self, query):
        """(label, start_ts, end_ts) for ?session=ID or ?minutes=N."""
        if "session" in query:
            name, start, end = self.server.pod_store.get_session_range(query["session"][0])
            return f"session-{query['session'][0]}-{name}", start, end
        minutes = int(query.get("minutes", ["60"])[0])
        if not 1 <= minutes <= MAX_EXPORT_MINUTES:
            raise ValidationError(f"minutes must be between 1 and {MAX_EXPORT_MINUTES}")
        end = time.time()
        return f"last-{minutes}-min", end - minutes * 60, end

    def _send_csv(self, text, filename):
        body = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _put_session(self):
        msg = self._read_json_body()
        if msg is None:
            return None
        store, hub = self.server.pod_store, self.server.pod_hub
        try:
            if not isinstance(msg, dict) or set(msg) - {"action", "name", "id"}:
                raise ValidationError('body must be {"action": "start" | "stop" | "delete", ...}')
            action = msg.get("action")
            if action == "start":
                session = store.start_session(msg.get("name"))
                event = store.add_event("info", "log", f"Recording started: {session['name']}")
            elif action == "stop":
                session = store.stop_session()
                event = store.add_event(
                    "info", "log", f"Recording stopped: {session['name']} ({session['readings']} readings)")
            elif action == "delete":
                name = store.delete_session(msg.get("id"))
                session = None
                event = store.add_event("info", "log", f"Session deleted: {name}")
            else:
                raise ValidationError('action must be "start", "stop" or "delete"')
        except ValidationError as err:
            return self._error(HTTPStatus.BAD_REQUEST, str(err))
        sessions = store.get_sessions()
        hub.publish("event", event)
        hub.publish("session", sessions)
        return self._send_json(HTTPStatus.OK, {"session": session, "sessions": sessions})

    def do_POST(self):  # noqa: N802
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "use PATCH /api/settings")

    do_DELETE = do_POST  # noqa: N815

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
        except ConnectionError:
            pass  # HUD closed or lost Wi-Fi (incl. Windows' ConnectionAbortedError)
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


def start_server(store, hub, host, port, static_dir, on_settings_changed=lambda: None, vr=None, vr_frame=None):
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.pod_store = store
    server.pod_hub = hub
    server.pod_vr = vr if vr is not None else VrState()
    server.pod_vr_frame = vr_frame if vr_frame is not None else VrFrame()
    server.pod_static_root = Path(static_dir).resolve()
    server.pod_on_settings_changed = on_settings_changed
    thread = threading.Thread(target=server.serve_forever, name="web", daemon=True)
    thread.start()
    log.info("HUD at http://%s:%s (static files from %s)", host, port, os.path.abspath(static_dir))
    return server
