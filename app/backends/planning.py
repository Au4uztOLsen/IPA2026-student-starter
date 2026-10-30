from app.planner import build_plan
# นำเข้าฟังก์ชัน build_plan ที่คุณเขียนไว้ใน Part 2 เอามาใช้งานที่นี่

def plan_interface(router, desired_interface, get_interface_state):
    """Build a Part 2 plan from backend status."""
    
    # 1. เรียกใช้งานฟังก์ชันที่รับเข้ามา (get_interface_state) 
    # เพื่อไปดึงค่าปัจจุบัน (Current State) ของอินเทอร์เฟซจาก Router
    response = get_interface_state(router, desired_interface["name"])
    
    # 2. เช็กว่าถ้าเกิด Error ในการเชื่อมต่อ ให้ตีกลับ Error นั้นไปเลย ไม่ต้องไปต่อ
    if response["status"] == "error":
        return response
        
    # 3. ดึงก้อนข้อมูล "interface" ออกมาจากผลลัพธ์ 
    # (ถ้าเจอข้อมูล จะได้เป็น Dictionary ถ้าไม่เจอ `response.get` จะคืนค่า None)
    current_interface = response.get("interface")
    
    # 4. โยนค่าที่อยากได้ (desired) และค่าปัจจุบัน (current) ไปให้ Part 2 ตัดสินใจ 
    # ว่าควร Create, Update หรือ No_change
    return build_plan(desired_interface, current_interface)