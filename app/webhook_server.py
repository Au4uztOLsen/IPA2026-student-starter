import json
import os
import requests
from pathlib import Path  # <-- เพิ่มการ import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
from tempfile import NamedTemporaryFile
from app.integration import process_request
from app.webex_client import WebexClient

class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor or process_request

    def handle_event(self, event):
        # สนใจแค่ messages/created และมี messageId
        if event.get("resource") != "messages" or event.get("event") != "created": return None
        data = event.get("data", {})
        message_id = data.get("id")
        if not message_id: return None

        # ข้ามข้อความที่ตัวเองส่ง (เช็คจาก payload เบื้องต้น)
        if data.get("personId") == self.bot_person_id: return None

        # โหลดข้อความจาก Webex
        message = self.client.get_message(message_id)
        
        # เช็คอีกครั้ง ป้องกันลูปจากการตอบกลับของบอท
        if message.get("personId") == self.bot_person_id:
            return None

        room_id = message["roomId"]
        
        files = message.get("files", [])
        if len(files) > 1:
            reply = {"status": "error", "result": "multiple_attachments"}
            self.client.send_message(room_id, json.dumps(reply))
            return reply
            
        attachment_path = None
        temp_file = None
        
        try:
            if len(files) == 1:
                file_content = self.client.download_file(files[0])
                temp_file = NamedTemporaryFile(delete=False, suffix=".yaml")
                temp_file.write(file_content)
                temp_file.close()
                attachment_path = Path(temp_file.name)  # <-- แปลงเป็น Path object ตรงนี้

            # ส่งเข้ากระบวนการประมวลผล
            result = self.processor(
                message.get("mentionedPeople", []),
                attachment_path,
                self.bot_person_id
            )
            
            # ส่งผลลัพธ์กลับเข้าห้อง
            self.client.send_message(room_id, json.dumps(result))
            return result
            
        finally:
            # ลบไฟล์ชั่วคราวทิ้งเสมอ
            if temp_file and os.path.exists(temp_file.name):
                os.remove(temp_file.name)

def make_http_handler(submit_event):
    class WebhookHTTPHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "result": "healthy"}).encode())
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path == "/webhook":
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    if not (1 <= content_length <= 1000000):
                        raise ValueError()
                    body = self.rfile.read(content_length)
                    event = json.loads(body)
                    if not isinstance(event, dict):
                        raise ValueError()
                        
                    # ตอบกลับ Webex ทันทีว่ารับทราบแล้ว
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "result": "accepted"}).encode())
                    
                    # โยนงานให้ Background Processing
                    submit_event(event)
                    
                except (ValueError, json.JSONDecodeError):
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "result": "invalid_event"}).encode())
            else:
                self.send_error(404)
    return WebhookHTTPHandler

def main():
    port = int(os.environ.get("WEBHOOK_PORT", 8000))
    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    
    client = WebexClient()
    bot_info = requests.get("https://webexapis.com/v1/people/me", headers=client.headers).json()
    bot_person_id = bot_info["id"]
    
    handler = WebexEventHandler(client, bot_person_id)
    executor = ThreadPoolExecutor(max_workers=1)
    
    def submit_event(event):
        executor.submit(handler.handle_event, event)
        
    server_class = make_http_handler(submit_event)
    server = ThreadingHTTPServer((host, port), server_class)
    server.serve_forever()

if __name__ == "__main__":
    main()