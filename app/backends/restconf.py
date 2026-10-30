import os
import requests
import urllib3
import ipaddress
from app.backends.planning import plan_interface as base_plan_interface

# ปิดแจ้งเตือน SSL กรณีใช้ self-signed certificate กับ Router
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_interface_state(router, interface_name, http_get=None):
    """Return normalized interface status using RESTCONF."""
    # สร้าง URL โดยใช้โครงสร้างของ IETF Model ระบุชื่อ Interface ลงไปท้าย URL
    url = f"/restconf/data/ietf-interfaces:interfaces/interface={interface_name}"
    
    # กรณีไม่ได้ส่งฟังก์ชันจำลองมา (เช่นรันระบบจริง) ให้สร้างฟังก์ชันยิง HTTP ขึ้นมาเอง
    if http_get is None:
        def real_http_get(path):
            full_url = f"https://{router}{path}"
            user = os.environ.get("ROUTER_USER")
            password = os.environ.get("ROUTER_PASS")
            headers = {"Accept": "application/yang-data+json"}
            return requests.get(full_url, auth=(user, password), headers=headers, verify=False, timeout=10)
        http_get = real_http_get
    
    try:
        # สั่งส่ง HTTP GET ไปดึงข้อมูล
        response = http_get(url)
        
        # จัดการ HTTP Status Code เบื้องต้น
        if response.status_code in (401, 403):
            return {"status": "error", "result": "authentication_failed"}
        if response.status_code == 404: #แปลว่าบนเครื่องไม่มี Interface นี้
            return {"status": "ok", "result": "not_found", "interface": None}
        if response.status_code >= 500: # ถ้าพังจากฝั่งระบบ
            return {"status": "error", "result": "backend_failed"}
        
        # แปลงผลลัพธ์จากข้อความเปล่าๆ เป็น JSON (Dictionary ใน Python) เพราะ router จะตอบกลับมาเป็นข้อความดิบๆ
        data = response.json()
        if "ietf-interfaces:interface" not in data:
            return {"status": "error", "result": "backend_failed"}
        # ถอดเอาเฉพาะเนื้อในที่อยู่ในคีย์ "ietf-interfaces:interface" มาใช้งาน    
        if_data = data["ietf-interfaces:interface"]
        
        # ถ้ามีคีย์ "enabled" และค่าเป็น True ให้ admin_state เป็น "up" (ถ้า False ก็ "down")
        admin_state = "up" if if_data.get("enabled", True) else "down"
        # ดึงคำอธิบายออกมา (ถ้าไม่มีจะเป็น None)
        description = if_data.get("description", None)
        
        ipv4 = None
        ipv4_list = if_data.get("ietf-ip:ipv4", {}).get("address", [])
        if ipv4_list:
            ip = ipv4_list[0].get("ip") # ได้เช่น "192.168.1.1"
            mask = ipv4_list[0].get("netmask") # ได้เช่น "255.255.255.0"
            if ip and mask:
                # เอา IP กับ Mask มาประมวลผลด้วยไลบรารี ipaddress เพื่อหา Prefix
                network = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
                ipv4 = f"{ip}/{network.prefixlen}" # จับมารวมร่างเป็น CIDR Format (เช่น 192.168.1.1/24)
        # จัด Format ให้ตรงกับตาราง Normalized Interface State ที่ Spec กำหนด        
        return {
            "status": "ok",
            "result": "found",
            "interface": {
                "name": if_data.get("name", interface_name),
                "ipv4": ipv4,
                "description": description,
                "admin_state": admin_state
            }
        }

    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except RuntimeError:
        return {"status": "error", "result": "backend_failed"}
    except Exception as e:
        if type(e).__name__ in ["Timeout", "ConnectionError"]:
            return {"status": "error", "result": "connection_failed"}
        return {"status": "error", "result": "backend_failed"}

def plan_interface(router, desired_interface, http_get=None):
    """Return create/update/no_change plan using RESTCONF status."""
    return base_plan_interface(
        router, 
        desired_interface, 
        lambda r, name: get_interface_state(r, name, http_get)
    )

def apply_interface(router, desired_interface, http_put=None):
    """Apply complete desired interface state using RESTCONF."""
    name = desired_interface["name"]
    # ตัดคำว่า "Loopback" ทิ้งให้เหลือแค่ตัวเลข เพราะ Cisco Native Model เอาแค่เลข!
    loopback_id = name.replace("Loopback", "")
    # สร้าง URL สำหรับส่งข้อมูลไปเขียนทับ (สังเกตว่าใช้ Cisco-IOS-XE-native ต่างจากตอน Get)
    url = f"https://{router}/restconf/data/Cisco-IOS-XE-native:native/interface/Loopback={loopback_id}"
    
    # กรณีไม่ได้ส่งฟังก์ชันจำลองมา (เช่นรันระบบจริง) ให้สร้างฟังก์ชันยิง HTTP ขึ้นมาเอง
    if http_put is None:
        def real_http_put(full_url, json):
            user = os.environ.get("ROUTER_USER")
            password = os.environ.get("ROUTER_PASS")
            headers = {
                "Accept": "application/yang-data+json",
                "Content-Type": "application/yang-data+json"
            }
            return requests.put(full_url, auth=(user, password), headers=headers, json=json, verify=False, timeout=10)
        http_put = real_http_put

    # หั่น "192.168.1.1/24" ออกเป็น ip ("192.168.1.1") กับ prefix ("24")
    ip, prefix = desired_interface["ipv4"].split("/")
    # แปลง Prefix ("24") กลับไปเป็น Subnet Mask ("255.255.255.0") เพื่อส่งเข้า Router
    mask = str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}", strict=False).netmask)
    
    payload = {
        "Cisco-IOS-XE-native:Loopback": {
            "name": int(loopback_id),
            "description": desired_interface["description"],
            "ip": {
                "address": {
                    "primary": {
                        "address": ip,
                        "mask": mask
                    }
                }
            }
        }
    }
    
    if desired_interface["admin_state"] == "down":
        payload["Cisco-IOS-XE-native:Loopback"]["shutdown"] = [None]
        
    try:
        response = http_put(url, json=payload)
        if response.status_code in (401, 403):
            return {"status": "error", "result": "authentication_failed"}
        if response.status_code not in (200, 201, 204):
            return {"status": "error", "result": "backend_failed"}
            
        return {"status": "ok", "result": "applied"}
        
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except RuntimeError:
        return {"status": "error", "result": "backend_failed"}
    except Exception as e:
        if type(e).__name__ in ["Timeout", "ConnectionError"]:
            return {"status": "error", "result": "connection_failed"}
        return {"status": "error", "result": "backend_failed"}