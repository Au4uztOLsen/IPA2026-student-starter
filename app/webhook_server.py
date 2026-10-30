import json
import os
import requests
import logging
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
from tempfile import NamedTemporaryFile
from app.integration import process_request
from app.webex_client import WebexClient

# เพิ่มการตั้งค่า logger[cite: 26]
log = logging.getLogger(__name__)

class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor or process_request

    def handle_event(self, event):
        # สนใจแค่ messages/created และมี messageId[cite: 25]
        if event.get("resource") != "messages" or event.get("event") != "created": return None
        data = event.get("data", {})
        message_id = data.get("id")
        if not message_id: return None

        # ข้ามข้อความที่ตัวเองส่ง (เช็คจาก payload เบื้องต้น)[cite: 25]
        if data.get("personId") == self.bot_person_id: return None

        # โหลดข้อความจาก Webex[cite: 25]
        message = self.client.get_message(message_id)
        
        # เช็คอีกครั้ง ป้องกันลูปจากการตอบกลับของบอท[cite: 25]
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
                attachment_path = Path(temp_file.name)

            # ส่งเข้ากระบวนการประมวลผล[cite: 25]
            result = self.processor(
                message.get("mentionedPeople", []),
                attachment_path,
                self.bot_person_id
            )
            
        except Exception:
            # ลบ raise ทิ้ง และเปลี่ยนเป็นการเก็บ log พร้อมคืนค่า backend_failed[cite: 26]
            log.exception('request failed')
            result = {'status': 'error', 'result': 'backend_failed'}
            
        finally:
            # ลบไฟล์ชั่วคราวทิ้งเสมอ[cite: 25]
            if temp_file and os.path.exists(temp_file.name):
                os.remove(temp_file.name)

        # ส่งผลลัพธ์กลับเข้าห้อง[cite: 25]
        self.client.send_message(room_id, json.dumps(result))
        return result

def make_http_handler(submit_event):
    # สร้างฟังก์ชันช่วยส่ง JSON
    def send_json(handler, code, payload):
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps(payload).encode())

    class WebhookHTTPHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            # ดัก Query String เผื่อมีการส่งพารามิเตอร์ต่อท้าย
            if self.path.split("?")[0] == "/health":
                send_json(self, 200, {"status": "ok", "result": "healthy"})
            else:
                # แก้ไขจาก self.send_error(404) เป็นส่ง JSON
                send_json(self, 404, {"status": "error", "result": "not_found"})

        def do_POST(self):
            if self.path.split("?")[0] == "/webhook":
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    if not (1 <= content_length <= 1000000):
                        raise ValueError()
                    body = self.rfile.read(content_length)
                    event = json.loads(body)
                    if not isinstance(event, dict):
                        raise ValueError()
                        
                    # ตอบกลับ Webex ทันทีว่ารับทราบแล้ว ด้วย JSON
                    send_json(self, 200, {"status": "ok", "result": "accepted"})
                    
                    # โยนงานให้ Background Processing[cite: 25]
                    submit_event(event)
                    
                except (ValueError, json.JSONDecodeError):
                    # ส่ง error กรณี payload ผิดปกติ
                    send_json(self, 400, {"status": "error", "result": "invalid_event"})
            else:
                # แก้ไขจาก self.send_error(404) เป็นส่ง JSON
                send_json(self, 404, {"status": "error", "result": "not_found"})
                
    return WebhookHTTPHandler

def main():
    logging.basicConfig(level=logging.INFO)
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