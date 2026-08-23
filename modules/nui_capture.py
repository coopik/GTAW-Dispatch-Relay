"""Read GTA World chat straight out of the running FiveM client.

FiveM does not save the chat anywhere. It lives in the game's local NUI page -
a small Chromium view - and is discarded when the frame is redrawn. Chromium
exposes a local debugging endpoint, though, so we can ask that page what it is
currently showing.

What this does, once every half second:

  1. GET http://127.0.0.1:13172/json  -> find the "nui://game/ui/root.html"
     target and take its webSocketDebuggerUrl.
  2. Open that WebSocket.
  3. Page.getFrameTree      -> walk it for the GTAW HUD frame.
  4. Page.createIsolatedWorld -> a private JS sandbox in that frame, so we can
     never collide with the HUD's own scripts.
  5. Runtime.evaluate      -> read the visible ".chat__messages > li" lines.

Everything is localhost-only and read-only. We never write to the game, never
touch its memory, and never send a single keystroke into it.

Limits worth knowing: we only see what is currently ON SCREEN, so if chat floods
faster than the poll interval and lines scroll out of the box, those lines are
gone. And the selector below is GTA World's HUD markup - if they change it, this
stops finding lines and the app falls back to the Chat Log Assistant's file.
"""

from __future__ import annotations

import io
import json
import os
import socket
import threading
import time

try:
    from modules import app_paths
except Exception:  # pragma: no cover - only when imported oddly
    app_paths = None

DEVTOOLS_HOST = "127.0.0.1"
DEVTOOLS_PORT = 13172
DEVTOOLS_TARGETS_URL = "http://%s:%d/json" % (DEVTOOLS_HOST, DEVTOOLS_PORT)
ROOT_UI_URL = "nui://game/ui/root.html"
CLIENT_FRAME_URL = "https://cfx-nui-client/web/index.html"
WORLD_NAME = "911-dispatch-relay-reader"
POLL_INTERVAL = 0.5
IDLE_INTERVAL = 2.0
OUTPUT_FILENAME = "live-session.txt"

# Reads every visible chat line, and digs the timestamp out of whichever
# attribute or ::before pseudo-element the HUD happens to keep it in.
CHAT_JS = (
    r"JSON.stringify(Array.from(document.querySelectorAll('.chat__messages > li'), el => {"
    r" const text = (el.innerText || '').replace(/\s+/g, ' ').trim();"
    r" if (!text) return '';"
    r" const nodes = [el].concat(Array.from(el.querySelectorAll('*')));"
    r" let timestamp = '';"
    r" for (const node of nodes) {"
    r"  for (const attribute of Array.from(node.attributes || [])) {"
    r"   const match = String(attribute.value).match(/\b\d{1,2}:\d{2}:\d{2}\b/);"
    r"   if (match) { timestamp = match[0]; break; }"
    r"  }"
    r"  if (!timestamp) {"
    r"   const match = String(getComputedStyle(node, '::before').content || '').match(/\b\d{1,2}:\d{2}:\d{2}\b/);"
    r"   if (match) timestamp = match[0];"
    r"  }"
    r"  if (timestamp) break;"
    r" }"
    r" return (timestamp ? '[' + timestamp + '] ' : '') + text;"
    r"}).filter(Boolean))"
)


class CaptureError(Exception):
    """The game, the debug port or the HUD was not available."""


# --------------------------------------------------------------------------- #
#  pure helpers - all of this is unit tested without a game or a socket
# --------------------------------------------------------------------------- #

def devtools_port_open(host: str = DEVTOOLS_HOST, port: int = DEVTOOLS_PORT,
                       timeout: float = 0.25) -> bool:
    """Cheap 'is FiveM up?' check - no process enumeration needed."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port)) == 0
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


def describe_exc(exc) -> str:
    """Never return an empty string - a bare 'failed:' in the log helps nobody."""
    text = str(exc or "").strip()
    return text or exc.__class__.__name__


def socket_open_error(detail: str) -> CaptureError:
    """Turn a raw WebSocket failure into something a human can act on.

    Chromium allows ONE debugger per page, and refuses the second with a 500, so
    that specific failure almost always means another chat tool got there first.
    """
    if "500" in detail or "Invalid response status" in detail:
        return CaptureError(
            "the chat debug socket is busy - another chat tool (usually the GTAW "
            "Log Parser / Chat Log Assistant) is attached to FiveM. Close it and "
            "capture takes over by itself")
    return CaptureError("could not open the NUI debug socket: %s" % detail)


def find_root_targets(targets) -> list:
    """Every FiveM root UI target, best first.

    There can be more than one, and a stale entry from a previous game session
    refuses the connection, so we try them all rather than trusting the first.
    """
    return [t for t in (targets or [])
            if isinstance(t, dict)
            and t.get("url") == ROOT_UI_URL
            and t.get("webSocketDebuggerUrl")]


def find_root_target(targets) -> dict:
    """Pick the FiveM root UI target out of /json."""
    for target in targets or []:
        if isinstance(target, dict) and target.get("url") == ROOT_UI_URL:
            return target
    raise CaptureError("FiveM root UI was not found on the debug port.")


def find_client_frame(frame_tree) -> dict:
    """Depth-first search for the GTAW HUD frame in a Page.getFrameTree result."""
    if not isinstance(frame_tree, dict):
        return {}
    frame = frame_tree.get("frame")
    if isinstance(frame, dict) and frame.get("url") == CLIENT_FRAME_URL:
        return frame
    for child in frame_tree.get("childFrames") or []:
        found = find_client_frame(child)
        if found:
            return found
    return {}


def parse_chat_payload(value) -> list:
    """Turn the JSON string Runtime.evaluate returned into a list of lines."""
    if isinstance(value, list):
        items = value
    else:
        try:
            items = json.loads(value or "[]")
        except (TypeError, ValueError):
            return []
    out = []
    for item in items or []:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def find_overlap(old_lines, new_lines) -> int:
    """Longest tail of the previous poll that starts the current poll.

    The chat box shows a rolling window, so consecutive polls overlap heavily.
    Whatever sits past the overlap is new chat.
    """
    max_len = min(len(old_lines), len(new_lines))
    for length in range(max_len, 0, -1):
        if list(old_lines[len(old_lines) - length:]) == list(new_lines[:length]):
            return length
    return 0


def has_timestamp(line: str) -> bool:
    body = (line or "").lstrip()
    if not body.startswith("["):
        return False
    end = body.find("]")
    if end < 0:
        return False
    inner = body[1:end]
    parts = inner.split(":")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def add_timestamp(line: str, now: float) -> str:
    if has_timestamp(line):
        return line
    return time.strftime("[%H:%M:%S] ", time.localtime(now)) + line


def session_header(now: float) -> str:
    stamp = time.localtime(now)
    return "[DATE: %s | TIME: %s]" % (time.strftime("%d/%b/%Y", stamp).upper(),
                                     time.strftime("%H:%M:%S", stamp))


def default_output_path() -> str:
    if app_paths is not None:
        try:
            return os.path.join(app_paths.user_data_dir(), OUTPUT_FILENAME)
        except Exception:
            pass
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "911 Dispatch Relay", OUTPUT_FILENAME)


# --------------------------------------------------------------------------- #
#  transport
# --------------------------------------------------------------------------- #

class AiohttpTransport:
    """Chrome DevTools Protocol over aiohttp, driven from one worker thread.

    aiohttp is already a dependency of the app, and getting WebSocket framing
    right by hand is not worth the risk, so we borrow theirs. The whole class is
    deliberately thin - everything interesting happens in CaptureEngine, which
    is testable with a fake transport.
    """

    def __init__(self, targets_url: str = DEVTOOLS_TARGETS_URL, timeout: float = 2.0):
        import asyncio
        import aiohttp  # noqa: F401  (import here so a missing dep is catchable)

        self._asyncio = asyncio
        self._aiohttp = aiohttp
        self.targets_url = targets_url
        self.timeout = float(timeout)
        self._loop = asyncio.new_event_loop()
        self._session = None
        self._ws = None
        self._req_id = 0

    def _run(self, coro):
        return self._loop.run_until_complete(
            self._asyncio.wait_for(coro, timeout=self.timeout))

    def list_targets(self) -> list:
        aiohttp = self._aiohttp

        async def go():
            async with aiohttp.ClientSession() as session:
                async with session.get(self.targets_url) as resp:
                    return await resp.json(content_type=None)

        try:
            return self._run(go()) or []
        except Exception as exc:
            raise CaptureError("debug port unreachable: %s" % describe_exc(exc))

    def open(self, ws_url: str) -> None:
        aiohttp = self._aiohttp

        async def go():
            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(ws_url, max_msg_size=0)

        try:
            self._run(go())
        except Exception as exc:
            self.close()
            raise socket_open_error(describe_exc(exc))

    def call(self, method: str, params: dict) -> dict:
        if self._ws is None:
            raise CaptureError("not connected")
        aiohttp = self._aiohttp
        self._req_id += 1
        request_id = self._req_id

        async def go():
            await self._ws.send_str(json.dumps(
                {"id": request_id, "method": method, "params": params or {}}))
            while True:
                msg = await self._ws.receive()
                if msg.type != aiohttp.WSMsgType.TEXT:
                    raise CaptureError("debug socket closed")
                data = json.loads(msg.data)
                if data.get("id") != request_id:
                    continue  # an unsolicited CDP event - ignore it
                if data.get("error"):
                    raise CaptureError("%s failed: %s" % (method, data["error"]))
                return data.get("result") or {}

        try:
            return self._run(go())
        except CaptureError:
            raise
        except Exception as exc:
            raise CaptureError("%s failed: %s" % (method, describe_exc(exc)))

    def close(self) -> None:
        async def go():
            if self._ws is not None:
                await self._ws.close()
            if self._session is not None:
                await self._session.close()

        try:
            self._loop.run_until_complete(go())
        except Exception:
            pass
        self._ws = None
        self._session = None
        self._req_id = 0

    def shutdown(self) -> None:
        self.close()
        try:
            self._loop.close()
        except Exception:
            pass


def default_transport_factory():
    return AiohttpTransport()


# --------------------------------------------------------------------------- #
#  engine
# --------------------------------------------------------------------------- #

class CaptureEngine:
    """Polls the game and appends what it sees to a plain text session file.

    The file is written in exactly the format the Chat Log Assistant uses, so
    the rest of the app - watcher, differ, parser - stays unchanged and stays
    tested. It also means you keep a readable log of your session.
    """

    def __init__(self, cfg=None, log=None, transport_factory=None,
                 output_path: str = "", port_check=None, clock=None):
        cfg = dict(cfg or {})
        self.log = log or (lambda _m: None)
        self.output_path = output_path or str(cfg.get("capture_path") or "") or default_output_path()
        self.poll_interval = max(0.2, float(cfg.get("capture_poll", POLL_INTERVAL) or POLL_INTERVAL))
        self._factory = transport_factory or default_transport_factory
        self._port_check = port_check or devtools_port_open
        self._clock = clock or time.time

        self.attached = False
        self.last_error = ""
        self.lines_written = 0
        self.attach_count = 0
        self.polls = 0

        self._transport = None
        self._context_id = 0
        self._previous = []
        self._stop = threading.Event()
        self._thread = None
        self._err_logged = ""

    # -- lifecycle ---------------------------------------------------------- #

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        folder = os.path.dirname(self.output_path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        if not os.path.exists(self.output_path):
            # Give the watcher a real file to attach to straight away, so you can
            # press Start before FiveM is even open.
            try:
                with io.open(self.output_path, "w", encoding="utf-8", newline="\n"):
                    pass
            except OSError as exc:
                self.log("Live capture: cannot write %s: %s" % (self.output_path, exc))
                return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="nui-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        self._thread = None
        self._detach()
        if self._transport is not None and hasattr(self._transport, "shutdown"):
            try:
                self._transport.shutdown()
            except Exception:
                pass
        self._transport = None

    def reset_baseline(self) -> None:
        """Forget what we have already seen (used when the log is cleared)."""
        self._previous = []

    def available(self) -> bool:
        return self.attached

    def status_text(self) -> str:
        if self.attached:
            return "Live capture: reading FiveM directly (%d lines)" % self.lines_written
        if self.last_error:
            return "Live capture: waiting - %s" % self.last_error
        return "Live capture: waiting for FiveM"

    # -- worker ------------------------------------------------------------- #

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self._cycle()
            except CaptureError as exc:
                worked = self._handle_failure(describe_exc(exc))
            except Exception as exc:  # never let the thread die
                worked = self._handle_failure(
                    "unexpected capture error: %s" % describe_exc(exc))
            self._stop.wait(self.poll_interval if worked else IDLE_INTERVAL)

    def _handle_failure(self, message: str) -> bool:
        """Closing FiveM kills the socket mid-call. That is not an error worth
        shouting about, so check the port before we blame anything."""
        was_attached = self.attached
        if not self._port_check():
            self._detach()
            self.last_error = "FiveM is not running"
            if was_attached and self._err_logged != "__closed__":
                self._err_logged = "__closed__"
                self.log("Live capture: FiveM closed.")
            return False
        self._fail(message)
        return False

    def _cycle(self) -> bool:
        if not self._port_check():
            # FiveM is closed. Next launch is a brand new session.
            if self.attached and self._err_logged != "__closed__":
                self._err_logged = "__closed__"
                self.log("Live capture: FiveM closed.")
            self._detach()
            self.last_error = "FiveM is not running"
            return False

        self._ensure_attached()
        self.polls += 1
        result = self._transport.call("Runtime.evaluate", {
            "expression": CHAT_JS,
            "contextId": self._context_id,
            "returnByValue": True,
        })
        value = (result.get("result") or {}).get("value")
        self._append(parse_chat_payload(value))
        self.last_error = ""
        self._err_logged = ""
        return True

    def _ensure_attached(self) -> None:
        if self.attached and self._transport is not None and self._context_id:
            return
        self._detach()
        transport = self._factory()
        self._transport = transport

        candidates = find_root_targets(transport.list_targets())
        if not candidates:
            raise CaptureError("FiveM's chat page has not started yet")

        frame = {}
        problem = None
        for target in candidates:
            try:
                transport.open(target["webSocketDebuggerUrl"])
                tree = transport.call("Page.getFrameTree", {})
            except CaptureError as exc:
                problem = exc
                try:
                    transport.close()
                except Exception:
                    pass
                continue
            frame = find_client_frame(tree.get("frameTree"))
            if frame.get("id"):
                break
            problem = CaptureError("the GTAW HUD is not loaded yet")
            frame = {}
            try:
                transport.close()
            except Exception:
                pass
        if not frame.get("id"):
            raise problem or CaptureError("the GTAW HUD is not loaded yet")

        world = transport.call("Page.createIsolatedWorld", {
            "frameId": frame["id"],
            "worldName": WORLD_NAME,
            # Yes, misspelled - that is the actual name in the DevTools protocol.
            "grantUniveralAccess": True,
        })
        context_id = world.get("executionContextId")
        if not context_id:
            raise CaptureError("the GTAW HUD context is unavailable")

        self._context_id = int(context_id)
        self.attached = True
        self.attach_count += 1
        self._previous = []
        self._truncate()
        self.log("Live capture: attached to FiveM - reading chat directly.")

    def _detach(self) -> None:
        if self._transport is not None:
            try:
                self._transport.close()
            except Exception:
                pass
        self.attached = False
        self._context_id = 0
        self._previous = []

    def _fail(self, message: str) -> None:
        self.attached = False
        self._context_id = 0
        self.last_error = message
        if message != self._err_logged:
            self._err_logged = message
            self.log("Live capture: %s" % message)

    # -- output ------------------------------------------------------------- #

    def _truncate(self) -> None:
        """A fresh attach means a fresh session, so start the file over."""
        try:
            with io.open(self.output_path, "w", encoding="utf-8", newline="\n"):
                pass
        except OSError as exc:
            raise CaptureError("cannot write %s: %s" % (self.output_path, exc))

    def _append(self, visible) -> None:
        current = [ln for ln in visible if ln.strip()]
        if not current:
            return
        overlap = find_overlap(self._previous, current)
        fresh = current[overlap:]
        self._previous = current
        if not fresh:
            return

        now = self._clock()
        try:
            start_of_session = (not os.path.exists(self.output_path)
                                or os.path.getsize(self.output_path) == 0)
            with io.open(self.output_path, "a", encoding="utf-8", newline="\n") as fh:
                if start_of_session:
                    fh.write(session_header(now) + "\n")
                for line in fresh:
                    fh.write(add_timestamp(line, now) + "\n")
        except OSError as exc:
            raise CaptureError("cannot write %s: %s" % (self.output_path, exc))
        self.lines_written += len(fresh)
