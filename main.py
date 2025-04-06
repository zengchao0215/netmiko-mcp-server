
import os
import logging
import sys
import tomllib

from netmiko import ConnectHandler
from netmiko import exceptions
from netmiko.ssh_dispatcher import platforms, telnet_platforms

from mcp.server.fastmcp import FastMCP



mcp = FastMCP("netmiko server", dependencies=["netmiko"])

class Device:
    name: str
    hostname: str
    device_type: str
    username: str
    password: str
    port: int
    identity: None | str

    def __init__(self, name:str = "", hostname:str = "", device_type:str = "",
                 username:str = "", password:str = "", port:int = 22):

        if not device_type in platforms + telnet_platforms:
            raise ValueError(f"name:{name}, invalid device_type: '{device_type}'")

        self.name = name
        self.hostname = hostname
        self.device_type = device_type
        self.username = username
        self.password = password
        self.port = port
    
    @property
    def connect_kwargs(self) -> dict:
        return {
            "host": self.hostname,
            "device_type": self.device_type,
            "username": self.username,
            "password": self.password,
            "port" : self.port,
            "conn_timeout" : 3,
            "read_timeout_override" : 20,
        }

    def send_command(self, cmd: str) -> str:
        with ConnectHandler(**self.connect_kwargs) as conn:
            output = conn.send_command(cmd)
        return str(output)    


def load_config_toml(tomlpath: str) -> dict[str, Device]:
    devs: dict[str, Device] = {}

    with open(tomlpath, "rb") as f:
        data = tomllib.load(f)

        default_args = {}
        if "default" in data:
            default_args = data["default"]

        for name, v in data.items():
            if name == "default":
                continue
            if not isinstance(v, dict):
                raise ValueError(f"unexpected value in toml: {v}")

            for default_k, default_v in default_args.items():
                v.setdefault(default_k, default_v)
            v.setdefault("name", name)

            devs[name] = Device(**v)
            
    return devs


@mcp.tool(description="Tool that returns list of network devices to which we can send command. Each line returns name of a device and its device_type (e.g., juniper, cisco, dell)")
def list_devices() -> list[str]:
    dev_strings = []
    devs = load_config_toml(sys.argv[1])
    for name, dev in sorted(devs.items(), key = lambda x: x[0]):
        dev_strings.append(f"Name:{name} DeviceType:{dev.device_type}")
    return dev_strings


@mcp.tool(description="Tool that sends a command to a network device specified by the name and returns its output. Note that acceptalbe commands depends on the device_type of the device you specified. You can get the list of name and device_type by using the list_device tool.")
def send_command_and_getoutput(name: str, command: str) -> str:
    devs = load_config_toml(sys.argv[1])
    if not name in devs:
        return f"Error: no device named '{name}'"

    try:
        ret = devs[name].send_command(command)
        return ret
    except exceptions.ConnectionException as e:
        return f"Connection Error: {e}"
        


def main():

    if len(sys.argv) < 2:
        print("usage: mcp-netmiko-server [CONFIG_TOML]", file = sys.stderr)
        sys.exit(1)

    # make sure the current config toml is valid
    load_config_toml(sys.argv[1])

    mcp.run()



if __name__ == "__main__":
    main()
