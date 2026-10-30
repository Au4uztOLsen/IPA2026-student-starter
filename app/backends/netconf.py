import ipaddress
import os
import xml.etree.ElementTree as ET
from ncclient import manager, NCClientError
from ncclient.transport.errors import AuthenticationError, SSHError
from ncclient.operations.rpc import RPCError
from app.backends.planning import plan_interface as base_plan_interface

def get_interface_state(router, interface_name, netconf_get_config=None):
    """Return normalized interface status using NETCONF."""
    
    if netconf_get_config is None:
        def real_get_config(router_host, filter_xml):
            user = os.environ.get("ROUTER_USER")
            password = os.environ.get("ROUTER_PASS")
            with manager.connect(
                host=router_host,
                port=830,
                username=user,
                password=password,
                hostkey_verify=False,
                device_params={'name': 'iosxe'},
                timeout=10
            ) as m:
                response = m.get_config(source='running', filter=('subtree', filter_xml))
                return response.data_xml
        netconf_get_config = real_get_config

    filter_xml = f"""
    <interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">
      <interface>
        <name>{interface_name}</name>
      </interface>
    </interfaces>
    """
    
    try:
        xml_text = netconf_get_config(router, filter_xml)
        root = ET.fromstring(xml_text)
        
        ns = {
            'if': 'urn:ietf:params:xml:ns:yang:ietf-interfaces',
            'ip': 'urn:ietf:params:xml:ns:yang:ietf-ip'
        }
        
        interface_node = root.find('.//if:interface', ns)
        if interface_node is None:
            return {"status": "ok", "result": "not_found", "interface": None}
            
        name_node = interface_node.find('if:name', ns)
        name = name_node.text if name_node is not None else interface_name
        desc_node = interface_node.find('if:description', ns)
        description = desc_node.text if desc_node is not None else None
        
        enabled_node = interface_node.find('if:enabled', ns)
        admin_state = "up"
        if enabled_node is not None and enabled_node.text == 'false':
            admin_state = "down"
            
        ip_node = interface_node.find('.//ip:ipv4/ip:address/ip:ip', ns)
        mask_node = interface_node.find('.//ip:ipv4/ip:address/ip:netmask', ns)
        
        ipv4 = None
        if ip_node is not None and mask_node is not None:
            network = ipaddress.IPv4Network(f"{ip_node.text}/{mask_node.text}", strict=False)
            ipv4 = f"{ip_node.text}/{network.prefixlen}"
            
        return {
            "status": "ok",
            "result": "found",
            "interface": {
                "name": name,
                "ipv4": ipv4,
                "description": description,
                "admin_state": admin_state
            }
        }
        
    except (PermissionError, AuthenticationError):
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, SSHError, TimeoutError, OSError):
        return {"status": "error", "result": "connection_failed"}
    except (RuntimeError, RPCError, NCClientError, ET.ParseError) as e:
        print(f"[netconf get_interface_state] Error: {e}")
        return {"status": "error", "result": "backend_failed"}
    except Exception as e:
        print(f"[netconf get_interface_state] Unexpected Error: {e}")
        return {"status": "error", "result": "backend_failed"}

def plan_interface(router, desired_interface, netconf_get_config=None):
    """Return create/update/no_change plan using NETCONF status."""
    return base_plan_interface(
        router, 
        desired_interface, 
        lambda r, name: get_interface_state(r, name, netconf_get_config)
    )

def apply_interface(router, desired_interface, netconf_edit_config=None):
    """Apply complete desired interface state using NETCONF."""
    
    if netconf_edit_config is None:
        def real_edit_config(router_host, config_xml):
            user = os.environ.get("ROUTER_USER")
            password = os.environ.get("ROUTER_PASS")
            with manager.connect(
                host=router_host,
                port=830,
                username=user,
                password=password,
                hostkey_verify=False,
                device_params={'name': 'iosxe'},
                timeout=10
            ) as m:
                m.edit_config(target='running', config=config_xml)
        netconf_edit_config = real_edit_config

    name = desired_interface["name"]
    loopback_id = name.replace("Loopback", "")
    ip, prefix = desired_interface["ipv4"].split("/")
    mask = str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}", strict=False).netmask)
    
    shutdown_tag = "<shutdown/>" if desired_interface["admin_state"] == "down" else ""
    
    config_xml = f"""
    <config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
      <native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">
        <interface>
          <Loopback nc:operation="replace">
            <name>{loopback_id}</name>
            <description>{desired_interface["description"]}</description>
            <ip>
              <address>
                <primary>
                  <address>{ip}</address>
                  <mask>{mask}</mask>
                </primary>
              </address>
            </ip>
            {shutdown_tag}
          </Loopback>
        </interface>
      </native>
    </config>
    """
    
    try:
        netconf_edit_config(router, config_xml)
        return {"status": "ok", "result": "applied"}
    except (PermissionError, AuthenticationError):
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, SSHError, TimeoutError, OSError):
        return {"status": "error", "result": "connection_failed"}
    except (RuntimeError, RPCError, NCClientError) as e:
        print(f"[netconf apply_interface] Error: {e}")
        return {"status": "error", "result": "backend_failed"}
    except Exception as e:
        print(f"[netconf apply_interface] Unexpected Error: {e}")
        return {"status": "error", "result": "backend_failed"}