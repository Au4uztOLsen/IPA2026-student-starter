from app.backends import ansible, netconf, netmiko_textfsm, restconf

def dispatch_request(data):
    action = data["action"]
    method = data["method"]
    router = data["router"]
    
    # ดึงข้อมูล interface ออกมา
    desired_interface = data.get("desired", {}).get("interface")
    interface_name = desired_interface["name"] if desired_interface else data.get("desired", {}).get("interface_name")
    
    if action == "status":
        # แก้ netmiko_textfsm เป็น netmiko-textfsm (ขีดกลาง)
        if method == "netmiko-textfsm": return netmiko_textfsm.get_interface_state(router, interface_name)
        if method == "restconf": return restconf.get_interface_state(router, interface_name)
        if method == "netconf": return netconf.get_interface_state(router, interface_name)
        
    elif action == "delete":
        # แก้ netmiko_textfsm เป็น netmiko-textfsm (ขีดกลาง)
        if method == "netmiko-textfsm": return netmiko_textfsm.delete_interface(router, interface_name)
        if method == "netconf": return netconf.delete_interface(router, interface_name)
        
    elif action == "apply":
        if method == "ansible": return ansible.apply_interface(router, desired_interface)
        if method == "restconf": return restconf.apply_interface(router, desired_interface)
        if method == "netconf": return netconf.apply_interface(router, desired_interface)
        
    elif action == "plan":
        # เปลี่ยนไปเรียก function plan_interface ของ backend โดยตรง
        if method == "restconf": return restconf.plan_interface(router, desired_interface)
        if method == "netconf": return netconf.plan_interface(router, desired_interface)
        if method == "netmiko-textfsm": return netmiko_textfsm.plan_interface(router, desired_interface)

    raise ValueError(f"Unsupported action/method: {action}/{method}")