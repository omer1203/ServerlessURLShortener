"""Local server for the frontend and the real shorten/redirect handlers.

Storage is in memory. Restarting the process forgets every link. This is a
development stand-in for API Gateway and DynamoDB, not a deployment target.

    PYTHONPATH=backend python3 -m devserver
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from handlers.redirect import handle_redirect_event
from handlers.shorten import handle_shorten_event
from urlshortener.config import Settings
from urlshortener.repository import InMemoryUrlRepository

FRONT_DIR = Path(__file__).resolve().parents[1] / "frontWeb"
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".json": "application/json; charset=utf-8",
    ".ico": "image/x-icon",
}


class DevServer(ThreadingHTTPServer):
    allow_reuse_address = True
    repo: InMemoryUrlRepository
    settings: Settings
    front_dir: Path


class AppHandler(BaseHTTPRequestHandler):
    server: DevServer

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/r/"):
            self._send_lambda(self._redirect_event("GET"))
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/shorten":
            self._send_bytes(404, "text/plain; charset=utf-8", b"Not found\n")
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 16_384:
            self._send_bytes(
                400,
                "application/json; charset=utf-8",
                b'{"error":"Request body is too large.","code":"invalid_json"}',
            )
            return
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        event = self._base_event("POST", path)
        event["body"] = raw
        event["headers"] = {"content-type": self.headers.get("Content-Type", "")}
        result = handle_shorten_event(event, None, self.server.settings, self.server.repo)
        self._send_lambda(result)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _redirect_event(self, method: str) -> dict[str, object]:
        path = urlparse(self.path).path
        code = unquote(path.removeprefix("/r/").split("/", 1)[0])
        event = self._base_event(method, path)
        event["pathParameters"] = {"code": code}
        return handle_redirect_event(event, None, self.server.settings, self.server.repo)

    def _base_event(self, method: str, path: str) -> dict[str, object]:
        host = self.server.settings.public_base_url.split("://", 1)[-1]
        return {
            "version": "2.0",
            "rawPath": path,
            "requestContext": {
                "requestId": "dev",
                "domainName": host,
                "stage": "$default",
                "http": {"method": method, "path": path},
            },
            "isBase64Encoded": False,
        }

    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        root = self.server.front_dir.resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            self._send_bytes(404, "text/plain; charset=utf-8", b"Not found\n")
            return
        if not candidate.is_file():
            self._send_bytes(404, "text/plain; charset=utf-8", b"Not found\n")
            return
        content_type = _CONTENT_TYPES.get(candidate.suffix, "application/octet-stream")
        data = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _send_lambda(self, result: dict[str, object]) -> None:
        status = int(result["statusCode"])  # type: ignore[arg-type]
        body = result.get("body") or ""
        if not isinstance(body, str):
            body = str(body)
        data = body.encode("utf-8")
        headers = result.get("headers") or {}
        self.send_response(status)
        if isinstance(headers, dict):
            for key, value in headers.items():
                self.send_header(str(key), str(value))
        self._cors()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, status: int, content_type: str, data: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")


def create_dev_server(port: int = 8000, front_dir: Path | None = None) -> DevServer:
    repo = InMemoryUrlRepository()
    front = front_dir or FRONT_DIR
    server = DevServer(
        ("127.0.0.1", port),
        AppHandler,
        bind_and_activate=True,
    )
    actual_port = server.server_address[1]
    server.repo = repo
    server.front_dir = front
    server.settings = Settings(
        table_name="local",
        public_base_url=f"http://127.0.0.1:{actual_port}",
        log_level="WARNING",
    )
    return server


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = create_dev_server(port)
    print(f"Shortlink dev server at {server.settings.public_base_url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
