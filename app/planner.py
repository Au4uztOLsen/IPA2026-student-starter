def build_plan(desired_interface, current_interface):
    """
    Compare desired interface state with normalized current state
    and return a plan according to specs/plan-spec-v1.md.
    """
    # ระบุฟิลด์ที่ Planner ต้องจัดการ (Managed Fields)
    managed_fields = ["ipv4", "description", "admin_state"]

    # 1. กรณีสร้างใหม่ (create): บน Router ยังไม่มี Interface นี้ (current_interface เป็น None)
    if current_interface is None:
        return {
            "status": "ok",
            "result": "planned",
            "operation": "create",
            "changes": {
                "ipv4": {"to": desired_interface.get("ipv4")},
                "description": {"to": desired_interface.get("description")},
                "admin_state": {"to": desired_interface.get("admin_state")}
            }
        }

    # 2. กรณีเปรียบเทียบข้อมูล (update หรือ no_change): บน Router มี Interface นี้อยู่แล้ว
    changes = {}
    
    # วนลูปเช็กทีละฟิลด์ว่ามีอะไรที่ "ค่าปัจจุบัน" ไม่ตรงกับ "ค่าที่ต้องการ" บ้าง
    for field in managed_fields:
        desired_val = desired_interface.get(field)
        current_val = current_interface.get(field)
        
        if desired_val != current_val:
            changes[field] = {
                "from": current_val,
                "to": desired_val
            }

    # 3. ตัดสินใจว่าเป็น update หรือ no_change โดยดูจากว่ามีการเก็บข้อมูลลงในตัวแปร changes หรือไม่
    if changes:  # ถ้า changes ไม่ว่างเปล่า แสดงว่ามีความต่าง = update
        return {
            "status": "ok",
            "result": "planned",
            "operation": "update",
            "changes": changes
        }
    else:        # ถ้า changes ว่างเปล่า แสดงว่าตรงกันทุกฟิลด์ = no_change
        return {
            "status": "ok",
            "result": "planned",
            "operation": "no_change",
            "changes": {}
        }