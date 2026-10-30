import yaml

def validate_request(data):
    """
    Validate one IPA2026 desired-state request.

    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    # 1. ตรวจสอบ version
    # ต้องมีคีย์ version, ประเภทต้องเป็น int (ไม่ใช่ boolean) และต้องมีค่าเป็น 1
    if 'version' not in data: #ดูว่ามี key version อยู่ใน dict หรือป่าว
        return {"status": "error", "result": "invalid_version"}
    
    version = data.get('version') #เอา value ของ key version ออกมา ด้วย method get ของ python ค่าน่าจะเป็น 1
    if type(version) is not int or isinstance(version, bool) or version != 1:
        return {"status": "error", "result": "invalid_version"}

    # 2. ตรวจสอบ router
    if 'router' not in data:
        return {"status": "error", "result": "missing_router"}
        
    router = data.get('router')
    allowed_routers = ["10.0.29.101", "10.0.29.102", "10.0.29.103", "10.0.29.104", "10.0.29.105"]
    if router not in allowed_routers:
        return {"status": "error", "result": "invalid_router"}

    # 3. ตรวจสอบ method ว่ามี method ที่รองรับไหม
    if 'method' not in data:
        return {"status": "error", "result": "missing_method"}
        
    method = data.get('method')
    allowed_methods = ["restconf", "netconf", "ansible", "netmiko-textfsm"] #list ของ method ที่ support
    if method not in allowed_methods: #ถ้า method ที่กรอกมาอยู่นอกเหนือใน list จะ return invalid method ไป
        return {"status": "error", "result": "invalid_method"}

    # 4. ตรวจสอบว่ามี key action ใน yaml ไหม
    if 'action' not in data:
        return {"status": "error", "result": "missing_action"}
        
    action = data.get('action')
    
    # เช็กความเข้ากันได้ของ Method กับ Action
    valid_combinations = {
        "restconf": ["status", "plan", "apply"],
        "netconf": ["status", "plan", "apply"],
        "ansible": ["apply"],
        "netmiko-textfsm": ["status", "delete"]
    }
    # ถ้า action ไม่อยู่ในลิสต์ที่ method นั้นรองรับ -> method คือตัวเเปรด้านบน ซึ่งเราจะเอาไป check ใน dict valid_combinations ถ้าไม่เจอ method จะคืนค่า list ว่าง (เผื่อไว้)
    if action not in valid_combinations.get(method, []): #เช็ค value ของ method ใน valid_combinations ถ้าไม่มีใน list ก็ return invalid_action
        return {"status": "error", "result": "invalid_action"}

    # 5. ตรวจสอบโครงสร้าง desired, interface และ name
    if 'desired' not in data or not isinstance(data['desired'], dict):
        return {"status": "error", "result": "missing_desired"}
    desired = data.get('desired') #desired เป็น dict ที่เก็บ interface ที่เป็น dict เหมือนกันอีกที

    if 'interface' not in desired or not isinstance(desired['interface'], dict):
        return {"status": "error", "result": "missing_interface"}
    interface = desired.get('interface') #interface เป็น dict ที่มี key name,ipv4, description เเละ admin_state อยู่

    if 'name' not in interface or interface.get('name') is None:
        return {"status": "error", "result": "missing_interface_name"}

    # 6. ตรวจสอบฟิลด์เพิ่มเติม (เฉพาะ plan และ apply)
    if action in ["plan", "apply"]:
        if 'ipv4' not in interface or interface.get('ipv4') is None:
            return {"status": "error", "result": "missing_ipv4"}
            
        if 'description' not in interface or interface.get('description') is None:
            return {"status": "error", "result": "missing_description"}
            
        if 'admin_state' not in interface or interface.get('admin_state') is None:
            return {"status": "error", "result": "missing_admin_state"}
            
        admin_state = interface.get('admin_state')
        if admin_state not in ["up", "down"]:
            return {"status": "error", "result": "invalid_admin_state"}

    return {
        "status": "ok", 
        "result": "accepted",
    }


def process_request_file(path):
    """
    Read a YAML request file, validate it,
    and return a response dictionary.
    """
    try:
        # เปิดไฟล์และอ่านเนื้อหา
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            
        # เช็กว่ารูปแบบไฟล์ที่โหลดมาเป็น Dictionary (Mapping) หรือไม่
        if not isinstance(data, dict):
            return {"status": "error", "result": "invalid_yaml"}
            
        # ถ้าโหลดสำเร็จและเป็น Dictionary ให้ส่งไปตรวจสอบ Key/Value ต่อ
        return validate_request(data)
        
    except yaml.YAMLError:
        # ถ้าเกิด Error ตอน Parse ไฟล์ (เช่น โครงสร้าง YAML ผิด)
        return {"status": "error", "result": "invalid_yaml"}
    except Exception:
        return {"status": "error", "result": "invalid_yaml"}
