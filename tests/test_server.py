"""HTTP routes, errors and concurrency of server.py."""

import http.client
import json
import socket
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from server import make_server


@pytest.fixture
def port() -> Iterator[int]:
    server = make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port
    server.shutdown()
    server.server_close()
    thread.join()


def request(
    port: int, method: str, path: str, body: bytes | None = None
) -> tuple[int, str, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    connection.request(method, path, body, headers)
    response = connection.getresponse()
    result = response.status, response.getheader("Content-Type", ""), response.read()
    connection.close()
    return result


def post(port: int, action: Any) -> tuple[int, Any]:
    status, _, body = request(port, "POST", "/api/action", json.dumps(action).encode())
    return status, json.loads(body)


@pytest.mark.parametrize(
    "path,content_type,text",
    [
        ("/", "text/html", b"<title>Chess workshop</title>"),
        ("/app.js", "text/javascript", b"addEventListener('keydown'"),
        ("/style.css", "text/css", b"#board"),
    ],
)
def test_static_files(port: int, path: str, content_type: str, text: bytes) -> None:
    status, kind, body = request(port, "GET", path)
    assert status == 200
    assert kind.startswith(content_type)
    assert text in body


def test_state_is_json(port: int) -> None:
    status, kind, body = request(port, "GET", "/api/state")
    assert status == 200 and kind == "application/json"
    state = json.loads(body)
    assert state["turn"] == "w" and state["moves"] == [] and len(state["board"]) == 32


@pytest.mark.parametrize("path", ["/index.html", "/server.py", "/../game.py", "/api"])
def test_unknown_paths_are_404(port: int, path: str) -> None:
    status, _, body = request(port, "GET", path)
    assert status == 404
    assert json.loads(body) == {"error": "Not found"}


def test_post_to_another_path_is_404(port: int) -> None:
    assert request(port, "POST", "/api/state", b"{}")[0] == 404


@pytest.mark.parametrize("body", [b"", b"not json", b"[1, 2]", b'"move"'])
def test_bad_request_bodies_are_400(port: int, body: bytes) -> None:
    status, _, response = request(port, "POST", "/api/action", body)
    assert status == 400
    assert "error" in json.loads(response)


@pytest.mark.parametrize(
    "action",
    [
        {"action": "fly"},
        {},
        {"action": "move", "source": "e2", "target": "e5"},
        {"action": "move", "source": None, "target": "e4"},
        {"action": "new", "opponent": "robot"},
    ],
)
def test_rejected_actions_are_400_and_change_nothing(port: int, action: Any) -> None:
    status, body = post(port, action)
    assert status == 400 and body["error"]
    assert json.loads(request(port, "GET", "/api/state")[2])["moves"] == []


def test_an_idle_connection_does_not_block_other_requests(port: int) -> None:
    # A browser may open a connection and send nothing (a preconnect). A server that
    # handles one connection at a time would wait on it and every request would hang.
    idle = socket.create_connection(("127.0.0.1", port))
    try:
        status, _, _ = request(port, "GET", "/api/state")
        assert status == 200
        assert post(port, {"action": "move", "source": "e2", "target": "e4"})[0] == 200
    finally:
        idle.close()


def test_concurrent_moves_keep_the_game_consistent(port: int) -> None:
    # Many clients try the same first move at once: exactly one may succeed.
    results: list[int] = []

    def try_move() -> None:
        results.append(
            post(port, {"action": "move", "source": "e2", "target": "e4"})[0]
        )

    threads = [threading.Thread(target=try_move) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [200] + [400] * 7
    state = json.loads(request(port, "GET", "/api/state")[2])
    assert state["moves"] == ["e2-e4"]
