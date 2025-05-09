
import argparse
import tomllib
import json

from netmiko import ConnectHandler
from netmiko import exceptions
from netmiko.ssh_dispatcher import platforms, telnet_platforms

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount

import logging
logger = logging.getLogger("mcp-netmiko-server")
logging.basicConfig(level=logging.INFO)


tomlpath: str|None = None
disable_config: bool = False

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

    def json(self) -> dict:
        return {
            "name": self.name,
            "hostname": self.hostname,
            "device_type": self.device_type
        }

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


    def send_config_set_and_commit_and_save(self, cmds: list[str]) -> str:
        with ConnectHandler(**self.connect_kwargs) as conn:
            output = conn.send_config_set(cmds)
            try:
                output += conn.commit()
            except AttributeError:
                pass

            try:
                output += conn.save_config()
            except NotImplementedError:
                pass

        return output




def load_config_toml() -> dict[str, Device]:
    devs: dict[str, Device] = {}

    if not tomlpath:
        raise RuntimeError("config toml is not specified")

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


@mcp.tool()
def get_network_device_list() -> str:
    """
    List all network devices that are accessible through this MCP server.

    This resource returns a list of objects representing network devices, including:
    - name: The name of the device
    - hostname: The IP address or hostname (domain name) of the device
    - device_type: The type (vendor and/or model) of this devie

    ## Example response structure:
    ```json
    [
        {
            "name": "nexus1",
            "hostname": 172.16.0.1,
            "device_type": "cisco_nexus"
        },
        {
            "name": "router1",
            "hostname": 172.16.0.2,
            "device_type": "juniper_junos"
        },
    ]
    ```

    ## How to use this information:
    1. Use `name` to specify a network device to control via `send_command_and_get_output` and `set_config_commands_and_commit_or_save` tools.
    2. Consider `device_type` to generate operational commands and configation commands depending on e.g., vendor, product, and operating systems.

    """

    logger.info("resource device list!!")
    devs = load_config_toml()
    return json.dumps([ dev.json() for dev in devs.values() ])


@mcp.tool()
def send_command_and_get_output(name: str, command: str) -> str:
    """

    Tool that sends a command to a network device specified by the name and returns its output.

    You can get available network devices via tool "get_network_device_list".

    ## Note
    - Acceptalbe commands depend on the device_type of the network device you specified. You should generate appropriate commands for the device_type.

    """
    devs = load_config_toml()

    if not name in devs:
        ret = f"Error: no device named '{name}'"
        logger.warning(f"get_output: {ret}")
        return ret

    try:
        ret = devs[name].send_command(command)
    except exceptions.ConnectionException as e:
        ret = f"Connection Error: {e}"

    logger.info(f"get: name={name} command='{command}' ret='{ret[:100]} ...'")

    return ret


@mcp.tool()
def set_config_commands_and_commit_or_save(name: str, commands: list[str]) -> str:

    """Tool that sends a series of configuration commands to a network device specified by the name.

    You can get available network devices via tool "get_network_device_list".

    ## Note
    - Acceptable configuration commands depdend on the device_type of the device you specified. You should generate appropriate configuration commands for the device_type.
    - After sending the commands, this tool automatically calls commit and save if necessary, and it returns their output.
    """

    if disable_config:
        return "changing configuration is prohibited"

    devs = load_config_toml()
    if not name in devs:
        ret = f"Error: no device named '{name}'"
        logger.warning(f"get_output: {ret}")
        return ret

    try:
        ret = devs[name].send_config_set_and_commit_and_save(commands)

    except exceptions.ConnectionException as e:
        ret = f"Connection Error: {e}"

    logger.info(f"set: name={name} command='{commands}' ret='{ret[:100]} ...'")

    return ret


def main():

    desc = "mcp-netmiko-server"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--disable-config", action="store_true",
                        help="disable chaning configuration")
    parser.add_argument("--sse", action="store_true",
                        help="run as an SSE server (default stdio)")
    parser.add_argument("--port", type=int, default = 10000,
                        help="port number for SSE server")
    parser.add_argument("--bind", type=str, default = "127.0.0.1",
                        help="bind address for SSE server")
    parser.add_argument("--debug", action="store_true",
                        help="enable starlette debug mode for SSE server")

    parser.add_argument("tomlpath", help = "path to config toml file")

    args = parser.parse_args()

    global tomlpath
    tomlpath = args.tomlpath

    global disable_config
    disable_config = args.disable_config

    # make sure the current config toml is valid
    load_config_toml()

    if args.sse:
        app = Starlette(
            debug=args.debug,
            routes = [
                Mount("/", app=mcp.sse_app())
            ]
        )

        import uvicorn
        uvicorn.run(app, host=args.bind, port=args.port)

    else:
        mcp.run()


if __name__ == "__main__":
    main()
