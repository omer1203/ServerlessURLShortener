from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

from devserver import create_dev_server


def test_dev_server_shortens_and_redirects() -> None:
    server = create_dev_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        page = HTTPConnection("127.0.0.1", port, timeout=5)
        page.request("GET", "/")
        home = page.getresponse()
        assert home.status == 200
        assert "text/html" in home.headers["Content-Type"]
        home.read()
        page.close()

        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        payload = json.dumps({"long_url": "https://example.com/from-dev"})
        conn.request("POST", "/shorten", body=payload, headers={"Content-Type": "application/json"})
        created = conn.getresponse()
        body = json.loads(created.read().decode())
        assert created.status == 201
        assert body["short_url"] == f"http://127.0.0.1:{port}/r/{body['short_code']}"
        conn.close()

        follow = HTTPConnection("127.0.0.1", port, timeout=5)
        follow.request("GET", f"/r/{body['short_code']}")
        redirected = follow.getresponse()
        redirected.read()
        assert redirected.status == 302
        assert redirected.headers["Location"] == "https://example.com/from-dev"
        follow.close()

        missing = HTTPConnection("127.0.0.1", port, timeout=5)
        missing.request("GET", "/r/ZZZZZZ")
        missed = missing.getresponse()
        missed.read()
        assert missed.status == 404
        missing.close()
    finally:
        server.shutdown()
        server.server_close()
