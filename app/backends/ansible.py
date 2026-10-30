import ipaddress
import json
import os
import subprocess

def apply_interface(router, desired_interface, run_playbook=None):
    """Apply complete desired interface state using Ansible via subprocess."""
    
    if run_playbook is None:
        def real_run_playbook(vars_dict):
            extravars = dict(vars_dict)
            
            # กำหนดค่าเชื่อมต่อ Network CLI สำหรับ Cisco IOS XE
            extravars["ansible_user"] = os.environ.get("ROUTER_USER")
            extravars["ansible_password"] = os.environ.get("ROUTER_PASS")
            extravars["ansible_connection"] = "ansible.netcommon.network_cli"
            extravars["ansible_network_os"] = "cisco.ios.ios"
            extravars["ansible_ssh_common_args"] = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
            
            playbook_path = os.path.join("ansible", "apply_interface.yml")
            if not os.path.exists(playbook_path):
                playbook_path = os.path.join("ansible", "apply_interface.yaml")

            cmd = [
                "ansible-playbook",
                playbook_path,
                "-i", f"{router},",
                "-e", json.dumps(extravars)
            ]
            
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30
            )
            
            # พิมพ์ Log เพื่อให้ตรวจสอบสาเหตุย่อยได้ผ่าน docker compose logs
            if proc.stdout:
                print(f"[ansible stdout]\n{proc.stdout}")

            if proc.returncode != 0:
                stdout_text = (proc.stdout or "").lower()
                
                if any(err in stdout_text for err in ["authentication failed", "invalid credentials", "permission denied", "authentication"]):
                    raise PermissionError("Ansible authentication failed")
                elif any(err in stdout_text for err in ["unreachable", "connection timed out", "connection refused", "timeout", "failed to connect", "host key"]):
                    raise ConnectionError("Ansible connection failed")
                else:
                    raise RuntimeError(f"Ansible playbook execution failed: {proc.stdout}")
                    
        run_playbook = real_run_playbook

    try:
        ip_obj = ipaddress.IPv4Interface(desired_interface["ipv4"])
        ip_address = str(ip_obj.ip)
        subnet_mask = str(ip_obj.netmask)

        variables = {
            "router": router,
            "interface_name": desired_interface["name"],
            "description": desired_interface["description"],
            "ipv4_address": ip_address,
            "netmask": subnet_mask,
            "shutdown": desired_interface["admin_state"] == "down"
        }
        
        run_playbook(variables)
        return {"status": "ok", "result": "applied"}
        
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except RuntimeError as e:
        print(f"[ansible apply_interface] Error: {e}")
        return {"status": "error", "result": "backend_failed"}
    except Exception as e:
        print(f"[ansible apply_interface] Unexpected Error: {e}")
        return {"status": "error", "result": "backend_failed"}