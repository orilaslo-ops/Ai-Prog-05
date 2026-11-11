"""One local game, served with Python's standard library."""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from session import Session

STATIC = Path(__file__).parent / "static"


def make_server(port: int = 8000) -> ThreadingHTTPServer:
    session = Session()
    # Each connection gets its own thread, so an idle one (such as a browser
    # preconnect) cannot hold up the others. The lock lets one request at a time
    # read or change the game.
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def respond(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, code: int, value: Any) -> None:
            self.respond(code, json.dumps(value).encode(), "application/json")

        def do_GET(self) -> None:
            if self.path == "/api/state":
                with lock:
                    state = json.dumps(session.view()).encode()
                self.respond(200, state, "application/json")
                return
            routes = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
            }
            if self.path not in routes:
                self.send_json(404, {"error": "Not found"})
                return
            name, content_type = routes[self.path]
            self.respond(200, (STATIC / name).read_bytes(), content_type)

        def do_POST(self) -> None:
            if self.path != "/api/action":
                self.send_json(404, {"error": "Not found"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1_000_000:
                    raise ValueError("Invalid request size")
                action = json.loads(self.rfile.read(size))
                if not isinstance(action, dict):
                    raise TypeError("Expected an action object")
                with lock:
                    result = json.dumps(session.dispatch(action)).encode()
            except (ValueError, TypeError) as error:
                self.send_json(400, {"error": str(error)})
                return
            self.respond(200, result, "application/json")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f"Open http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
