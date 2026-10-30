from .core import process_request_file

def validate_webex_envelope(
    mentioned_people,
    attachment_path,
    bot_person_id,
):
    # ตรวจสอบว่า bot_person_id เป็น string ที่มีความยาว และอยู่ใน list ของ mentioned_people หรือไม่
    if not isinstance(bot_person_id, str) or not bot_person_id:
        return {"status": "error", "result": "missing_bot_mention"}

    #bot person id ต้องอยู่ใน list mentioned people
    if not isinstance(mentioned_people, list) or bot_person_id not in mentioned_people:
        return {"status": "error", "result": "missing_bot_mention"}
        
    # ตรวจสอบการแนบไฟล์ yaml โดย attachment_path เป็นที่อยู่ของไฟล์ yaml ที่เราเเนบไปใน webex ถ้าเราไม่ได้เเนบไฟล์ไป จะมีค่าเป็น none
    if attachment_path is None:
        return {"status": "error", "result": "no_yaml"}
        
    return None


def handle_webex_request(
    mentioned_people,
    attachment_path,
    bot_person_id,
):
    """
    Validate the envelope, then validate the attached YAML request.
    Return a response dictionary. Do not dispatch to a router.
    """
    envelope_error = validate_webex_envelope(
        mentioned_people, attachment_path, bot_person_id
    )

    if envelope_error is not None:
        return envelope_error

    #ส่งไฟล์ yaml ไปตรวจสอบโครงสร้างไฟล์ yaml เเล้ว return
    return process_request_file(attachment_path)

