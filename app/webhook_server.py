from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from app.integration import process_request
from app.webex_client import WEBEX_API_BASE, WebexClient


class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor or process_request

    def handle_event(self, event):
        if not isinstance(event, dict):
            return None
        if event.get("resource") != "messages" or event.get("event") != "created":
            return None

        data = event.get("data", {})
        if not isinstance(data, dict):
            return None

        message_id = data.get("id")
        if not message_id:
            return None

        if data.get("personId") == self.bot_person_id:
            return None

        message = self.client.get_message(message_id)

        if message.get("personId") == self.bot_person_id:
            return None

        room_id = message.get("roomId")
        mentioned_people = message.get("mentionedPeople", [])
        files = message.get("files", [])

        if len(files) > 1:
            result = {"status": "error", "result": "multiple_attachments"}
        elif len(files) == 1:
            file_bytes = self.client.download_file(files[0])
            with TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir) / "request.yaml"
                tmp_path.write_bytes(file_bytes)
                try:
                    result = self.processor(mentioned_people, tmp_path, self.bot_person_id)
                finally:
                    if tmp_path.exists():
                        tmp_path.unlink()
        else:
            result = self.processor(mentioned_people, None, self.bot_person_id)

        if room_id and result is not None:
            self.client.send_message(room_id, json.dumps(result))

        return result


def make_http_handler(submit_event):
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "result": "healthy"}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/webhook":
                length = int(self.headers.get("Content-Length", 0))
                if length < 1 or length > 1_000_000:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "result": "invalid_event"}).encode())
                    return

                raw_body = self.rfile.read(length)
                try:
                    event_data = json.loads(raw_body.decode("utf-8"))
                    if not isinstance(event_data, dict):
                        raise ValueError()
                except Exception:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "result": "invalid_event"}).encode())
                    return

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "result": "accepted"}).encode())

                submit_event(event_data)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    return RequestHandler


def main():
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

    token = os.getenv("WEBEX_BOT_TOKEN")
    client = WebexClient(token=token)

    resp = client.session.get(f"{WEBEX_API_BASE}/people/me", headers=client.headers, timeout=10)
    resp.raise_for_status()
    bot_person_id = resp.json().get("id")

    handler = WebexEventHandler(client, bot_person_id)

    executor = ThreadPoolExecutor(max_workers=1)

    host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.getenv("WEBHOOK_PORT", 8000))

    server = ThreadingHTTPServer((host, port), make_http_handler(lambda ev: executor.submit(handler.handle_event, ev)))
    print(f"Webhook server started at http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        executor.shutdown(wait=True)


if __name__ == "__main__":
    main()