import yaml
from app.dispatcher import dispatch_request
from app.request_handler import handle_webex_request

def process_request(mentioned_people, attachment_path, bot_person_id):
    # 1. ตรวจสอบ Envelope และความถูกต้องของไฟล์ YAML
    validation_result = handle_webex_request(
        mentioned_people, 
        attachment_path, 
        bot_person_id
    )

    # 2. หากมี Error ให้ส่งกลับทันที
    if validation_result.get("status") == "error":
        return validation_result

    # 3. เมื่อผ่านแล้ว โหลดไฟล์ YAML เพื่อส่งต่อให้ Dispatcher
    with open(attachment_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return dispatch_request(data)