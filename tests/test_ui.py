import http.client
import json
import socket
import threading
from http.server import ThreadingHTTPServer

import pytest
from conftest import switch_to_mysql


@pytest.fixture
def server(repo):
    from mender import gitutil, queue, ui
    from mender.models import Draft, QueueItem
    repo.store.remember("Our project runs on Postgres", ["docker-compose.yml"])
    switch_to_mysql(repo)
    queue.add(QueueItem("m1", "replace", "Our project runs on Postgres", ["docker-compose.yml"], "why",
                        Draft("Our project runs on MySQL", "r", 0.9), "diff",
                        file_hashes={"docker-compose.yml": gitutil.blob_hash("docker-compose.yml")}))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = ThreadingHTTPServer(("127.0.0.1", port), ui.make_handler("tok", port))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield port, repo
    srv.shutdown(); srv.server_close()


def call(port, method, path, body=None, headers=None, host=None):
    c = http.client.HTTPConnection("127.0.0.1", port)
    h = {"Host": host or f"127.0.0.1:{port}", **(headers or {})}
    if body is not None:
        h.setdefault("Content-Type", "application/json")
    c.request(method, path, json.dumps(body) if body is not None else None, h)
    r = c.getresponse()
    data = r.read()
    return r.status, data


def test_page_and_state(server):
    port, _ = server
    st, page = call(port, "GET", "/")
    assert st == 200 and b"Mender review" in page and b"tok" in page
    st, data = call(port, "GET", "/api/state")
    s = json.loads(data)
    assert st == 200 and s["items"][0]["id"] == "m1"
    assert s["items"][0]["draft"]["new_text"] == "Our project runs on MySQL"
    assert s["items"][0]["drifted"] is False


def test_writes_need_token_and_local_host(server):
    port, _ = server
    assert call(port, "POST", "/api/approve", {"id": "m1"})[0] == 403                    # no token
    assert call(port, "POST", "/api/approve", {"id": "m1"}, {"X-Mender-Token": "bad"})[0] == 403
    assert call(port, "GET", "/api/state", host="evil.example.com")[0] == 403             # DNS rebinding
    assert call(port, "POST", "/api/approve", {"id": "m1"},
                {"X-Mender-Token": "tok", "Content-Type": "text/plain"})[0] == 415


def test_approve_through_ui(server):
    port, repo = server
    st, data = call(port, "POST", "/api/approve", {"id": "m1", "text": "Database: MySQL 8"},
                    {"X-Mender-Token": "tok"})
    assert st == 200
    assert repo.store.mem["m2"]["text"] == "Database: MySQL 8"
    assert json.loads(call(port, "GET", "/api/state")[1])["items"] == []


def test_ui_refuses_drifted_draft(server):
    port, repo = server
    (repo.path / "docker-compose.yml").write_text("changed again\n")
    assert json.loads(call(port, "GET", "/api/state")[1])["items"][0]["drifted"] is True
    st, data = call(port, "POST", "/api/approve", {"id": "m1"}, {"X-Mender-Token": "tok"})
    assert st == 409 and repo.store.n == 1


def test_reject_through_ui(server):
    port, _ = server
    assert call(port, "POST", "/api/reject", {"id": "m1"}, {"X-Mender-Token": "tok"})[0] == 200
    assert call(port, "POST", "/api/reject", {"id": "m1"}, {"X-Mender-Token": "tok"})[0] == 400
