import ipaddress
import os
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

def _extract_val(d, keys):
    for k in keys:
        if k in d:
            v = d[k]
            if isinstance(v, list):
                return v[0] if v else None
            return v
    return None

def get_interface_state(router, interface_name, netmiko_get=None):
    """Return normalized interface status using Netmiko + TextFSM."""
    
    if netmiko_get is None:
        def real_netmiko_get(router_host, intf_name):
            device = {
                'device_type': 'cisco_ios',
                'host': router_host,
                'username': os.environ.get("ROUTER_USER"),
                'password': os.environ.get("ROUTER_PASS"),
                'global_delay_factor': 2,
            }
            with ConnectHandler(**device) as net_connect:
                # ดักจับ TextFSM Parsing Error ถ้ารูปแบบคำตอบผิดปกติ (มักเกิดตอน Interface ไม่มี)
                try:
                    ip_info = net_connect.send_command(f"show ip interface {intf_name}", use_textfsm=True)
                except Exception as e:
                    if "State Error" in str(e) or "TextFSM" in str(e):
                        ip_info = []
                    else:
                        raise e

                try:
                    desc_info = net_connect.send_command("show interfaces description", use_textfsm=True)
                except Exception as e:
                    if "State Error" in str(e) or "TextFSM" in str(e):
                        desc_info = []
                    else:
                        raise e
                
                if isinstance(ip_info, str): ip_info = []
                if isinstance(desc_info, str): desc_info = []
                
                return ip_info, desc_info
        netmiko_get = real_netmiko_get

    try:
        ip_info, descriptions = netmiko_get(router, interface_name)
        
        short_name = interface_name.replace("Loopback", "Lo")
        
        desc = None
        if descriptions:
            for row in descriptions:
                port = _extract_val(row, ["port", "interface", "intf", "name"])
                if port in (interface_name, short_name):
                    desc = _extract_val(row, ["description", "desc", "alias"])
                    break
        
        if not ip_info:
            return {"status": "ok", "result": "not_found", "interface": None}
            
        target_info = None
        for row in ip_info:
            port = _extract_val(row, ["interface", "intf", "port", "name"])
            if port in (interface_name, short_name):
                target_info = row
                break
                
        if not target_info:
            return {"status": "ok", "result": "not_found", "interface": None}
            
        if not desc:
            desc = _extract_val(target_info, ["description", "desc"])
            
        status_text = str(_extract_val(target_info, ["link_status", "status", "admin_state", "state"]) or "").lower()
        admin_state = "down" if "down" in status_text else "up"
        
        ip = _extract_val(target_info, ["ip_address", "ipaddr", "ip"])
        prefix = _extract_val(target_info, ["prefix_length", "mask", "prefix"])
        ipv4 = f"{ip}/{prefix}" if ip and prefix else None
        
        return {
            "status": "ok",
            "result": "found",
            "interface": {
                "name": interface_name,
                "ipv4": ipv4,
                "description": desc,
                "admin_state": admin_state
            }
        }

    except (PermissionError, NetmikoAuthenticationException):
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, NetmikoTimeoutException):
        return {"status": "error", "result": "connection_failed"}
    except RuntimeError:
        return {"status": "error", "result": "backend_failed"}
    except Exception as e:
        print(f"[get_interface_state] Error: {e}")
        return {"status": "error", "result": "backend_failed"}

def delete_interface(router, interface_name, netmiko_delete=None):
    """Delete an interface using Netmiko."""
    
    if netmiko_delete is None:
        def real_netmiko_delete(router_host, intf_name):
            state = get_interface_state(router_host, intf_name)
            
            if state.get("status") == "error":
                if state.get("result") == "authentication_failed":
                    raise PermissionError("Cannot authenticate to router")
                elif state.get("result") == "connection_failed":
                    raise ConnectionError("Cannot connect to router")
                else:
                    raise RuntimeError("Backend operation failed during initial state check")
            
            if state.get("result") == "not_found":
                return "not_found"
                
            device = {
                'device_type': 'cisco_ios',
                'host': router_host,
                'username': os.environ.get("ROUTER_USER"),
                'password': os.environ.get("ROUTER_PASS"),
            }
            with ConnectHandler(**device) as net_connect:
                commands = [f"no interface {intf_name}"]
                net_connect.send_config_set(commands)
            
            post_state = get_interface_state(router_host, intf_name)
            if post_state.get("result") == "not_found":
                return "deleted"
            return "backend_failed"
                
        netmiko_delete = real_netmiko_delete

    try:
        result = netmiko_delete(router, interface_name)
        
        if result == "not_found":
            return {"status": "ok", "result": "not_found", "interface": None}
        elif result == "deleted":
            return {"status": "ok", "result": "deleted"}
        else:
            return {"status": "error", "result": "backend_failed"}
            
    except (PermissionError, NetmikoAuthenticationException):
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, NetmikoTimeoutException):
        return {"status": "error", "result": "connection_failed"}
    except RuntimeError:
        return {"status": "error", "result": "backend_failed"}
    except Exception as e:
        print(f"[delete_interface] Error: {e}")
        return {"status": "error", "result": "backend_failed"}