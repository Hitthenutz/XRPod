"""
A small MQTT 3.1.1 client using only the Python standard library.

The Pi runs the broker (Mosquitto) and talks to the ESP32 nodes through it.
This client covers what the agent needs and nothing more:
  * connect (clean session, optional username/password),
  * subscribe and publish at QoS 0,
  * keepalive pings, and reconnect with backoff if the broker goes away.

It runs its own background thread. on_message(topic, payload) is called from
that thread with the topic as str and the payload as bytes; keep it short.
"""

import logging
import os
import socket
import struct
import threading
import time

log = logging.getLogger("xrpod.mqtt")

# MQTT packet types (the first 4 bits of every packet)
CONNECT, CONNACK, PUBLISH, PUBACK = 1, 2, 3, 4
SUBSCRIBE, SUBACK, PINGREQ, PINGRESP, DISCONNECT = 8, 9, 12, 13, 14

MAX_PACKET = 64 * 1024  # our messages are tiny; anything bigger is junk
CONNACK_ERRORS = {
    1: "unsupported protocol version",
    2: "client id rejected",
    3: "broker unavailable",
    4: "bad username or password",
    5: "not authorized",
}


class ProtocolError(Exception):
    pass


# --------------------------------------------------------------------------
# Building packets
# --------------------------------------------------------------------------
def encode_length(n):
    """MQTT 'remaining length': 7 bits per byte, high bit = more bytes."""
    if not 0 <= n <= 268_435_455:
        raise ValueError("packet too large")
    out = bytearray()
    while True:
        byte, n = n % 128, n // 128
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def encode_str(s):
    """MQTT strings: 2-byte length, then the UTF-8 bytes."""
    data = s.encode("utf-8") if isinstance(s, str) else bytes(s)
    if len(data) > 65535:
        raise ValueError("string too long")
    return struct.pack("!H", len(data)) + data


def packet(ptype, flags, body=b""):
    """Every packet: 1 header byte (type + flags), the length, then the body."""
    return bytes([(ptype << 4) | flags]) + encode_length(len(body)) + body


def connect_packet(client_id, keepalive, username=None, password=None):
    flags = 0x02  # clean session
    payload = encode_str(client_id)
    if username is not None:
        flags |= 0x80
        payload += encode_str(username)
        if password is not None:
            flags |= 0x40
            payload += encode_str(password)
    body = encode_str("MQTT") + bytes([4, flags]) + struct.pack("!H", keepalive)
    return packet(CONNECT, 0, body + payload)


def subscribe_packet(packet_id, topics):
    body = struct.pack("!H", packet_id)
    for topic in topics:
        body += encode_str(topic) + b"\x00"  # QoS 0
    return packet(SUBSCRIBE, 0x02, body)


def publish_packet(topic, payload, retain=False):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return packet(PUBLISH, 0x01 if retain else 0, encode_str(topic) + payload)

# --------------------------------------------------------------------------
# Reading packets
# --------------------------------------------------------------------------
def parse_packet(buf):
    """Take one complete packet off the front of `buf` (a bytearray).
    Returns (type, flags, body), or None if more bytes are needed."""
    if len(buf) < 2:
        return None
    length, multiplier, i = 0, 1, 1
    while True:
        if i >= len(buf):
            return None
        byte = buf[i]
        length += (byte & 0x7F) * multiplier
        i += 1
        if not byte & 0x80:
            break
        multiplier *= 128
        if i > 4:
            raise ProtocolError("bad remaining length")
    if length > MAX_PACKET:
        raise ProtocolError(f"packet too large ({length} bytes)")
    if len(buf) < i + length:
        return None
    header = buf[0]
    body = bytes(buf[i:i + length])
    del buf[:i + length]
    return header >> 4, header & 0x0F, body


def parse_publish(flags, body):
    """(topic, payload, qos, packet_id) from an incoming PUBLISH body."""
    if len(body) < 2:
        raise ProtocolError("short publish")
    (tlen,) = struct.unpack("!H", body[:2])
    if len(body) < 2 + tlen:
        raise ProtocolError("short publish topic")
    try:
        topic = body[2:2 + tlen].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolError("topic is not UTF-8") from exc
    rest = body[2 + tlen:]
    qos = (flags >> 1) & 0x03
    packet_id = None
    if qos:
        if len(rest) < 2:
            raise ProtocolError("missing packet id")
        (packet_id,) = struct.unpack("!H", rest[:2])
        rest = rest[2:]
    return topic, rest, qos, packet_id

# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------
class MqttClient:
    def __init__(self, host, port=1883, client_id=None, username=None, password=None,
                 keepalive=30, subscriptions=(), on_message=None):
        self.host, self.port = host, port
        self.client_id = client_id or "xrpod-pi-" + os.urandom(3).hex()
        self.username, self.password = username, password
        self.keepalive = keepalive
        self.subscriptions = list(subscriptions)
        self.on_message = on_message
        self._sock = None
        self._send_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._last_sent = 0.0
        self._last_heard = 0.0
        self.connected = False

    # ---- public API --------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, name="mqtt", daemon=True)
        self._thread.start()

    def publish(self, topic, payload, retain=False):
        """Send now. Returns False if not connected (the message is dropped;
        callers that matter resend on their own schedule)."""
        return self._send(publish_packet(topic, payload, retain))

    def close(self):
        self._stop.set()
        if self.connected:
            self._send(packet(DISCONNECT, 0))
        self._drop()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)

    # ---- internals ---------------------------------------------------------
    def _send(self, data):
        with self._send_lock:
            sock = self._sock
            if sock is None or not self.connected and data[0] >> 4 != CONNECT:
                return False
            try:
                sock.sendall(data)
            except OSError as exc:
                log.warning("mqtt: send failed: %s", exc)
                return False
            self._last_sent = time.monotonic()
            return True

    def _drop(self):
        self.connected = False
        with self._send_lock:
            sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    def _run(self):
        """Background thread: stay connected until close() is called."""
        backoff = 1
        while not self._stop.is_set():
            try:
                self._session()
                backoff = 1
            except (OSError, ProtocolError) as exc:
                if not self._stop.is_set():
                    log.warning("mqtt: %s:%s %s; retrying in %ss", self.host, self.port, exc, backoff)
            finally:
                was_connected = self.connected
                self._drop()
                if was_connected:
                    log.warning("mqtt: disconnected from broker")
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 30)

    def _session(self):
        """One connection: connect, subscribe, then read until it breaks."""
        sock = socket.create_connection((self.host, self.port), timeout=5)
        with self._send_lock:
            self._sock = sock
        self._send(connect_packet(self.client_id, self.keepalive, self.username, self.password))
        buf = bytearray()
        ptype, _, body = self._read_packet(sock, buf, deadline=time.monotonic() + 5)
        if ptype != CONNACK or len(body) < 2:
            raise ProtocolError("expected CONNACK")
        if body[1] != 0:
            raise ProtocolError("broker refused: " + CONNACK_ERRORS.get(body[1], f"code {body[1]}"))
        self.connected = True
        self._last_heard = time.monotonic()
        log.info("mqtt: connected to %s:%s", self.host, self.port)
        if self.subscriptions:
            self._send(subscribe_packet(1, self.subscriptions))

        sock.settimeout(1)
        while not self._stop.is_set():
            now = time.monotonic()
            # Ping if we have not sent OR not heard anything for a while. The Pi
            # resends commands every few seconds, so checking only "sent" never
            # pinged, heard nothing back, and dropped a healthy broker.
            if now - min(self._last_sent, self._last_heard) >= self.keepalive / 2:self._send(packet(PINGREQ, 0))
            if now - self._last_heard > self.keepalive * 1.5:
                raise ProtocolError("broker stopped answering")
            try:
                data = sock.recv(4096)
            except TimeoutError:
                continue
            if not data:
                raise ProtocolError("broker closed the connection")
            self._last_heard = time.monotonic()
            buf += data
            while True:
                pkt = parse_packet(buf)
                if pkt is None:
                    break
                self._handle(*pkt)

    def _read_packet(self, sock, buf, deadline):
        """Wait for one whole packet (used for the CONNACK)."""
        while True:
            pkt = parse_packet(buf)
            if pkt is not None:
                return pkt
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProtocolError("timed out waiting for the broker")
            sock.settimeout(remaining)
            data = sock.recv(4096)
            if not data:
                raise ProtocolError("broker closed the connection")
            buf += data

    def _handle(self, ptype, flags, body):
        if ptype == PUBLISH:
            topic, payload, qos, packet_id = parse_publish(flags, body)
            if qos == 1:
                self._send(packet(PUBACK, 0, struct.pack("!H", packet_id)))
            if self.on_message:
                try:
                    self.on_message(topic, payload)
                except Exception:
                    log.exception("mqtt: error handling a message on %s", topic)
        # CONNACK again, SUBACK, PINGRESP, PUBACK: nothing to do.
                    