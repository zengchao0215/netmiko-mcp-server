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
secured_mode: bool = False

destructive_command_prefixes = [
    "r", # request, restart, reload, etc
    "clear",
    "copy",
    "file",
    "write",
    "delete",
    "shut",
    "start",
    "power",
    "debug",
    "lock",
    "set"
]


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
        kwargs = {
            "host": self.hostname,
            "device_type": self.device_type,
            "username": self.username,
            "password": self.password,
            "port": self.port,
            "conn_timeout": 10,               # 增加连接超时时间
            "read_timeout_override": 60,      # 增加读取超时时间
            "session_log": "netmiko_session.log",  # 用于调试连接问题
            "global_delay_factor": 3,         # 全局延迟因子
            "fast_cli": False,               # 禁用快速CLI
            "secret": self.password,         # enable密码
            "banner_timeout": 20             # banner超时时间
        }
        
        # 为 telnet 设备添加额外参数
        if "_telnet" in self.device_type:
            kwargs.update({
                "session_timeout": 60,       # telnet会话超时
                "blocking_timeout": 20       # 阻塞超时
            })
        # print("connect_kwargs: ", kwargs)
        return kwargs

    def send_command(self, cmd: str) -> str:
        try:
            with ConnectHandler(**self.connect_kwargs) as conn:
                output = conn.send_command(cmd)
        except Exception as e:
            print(f"连接或命令执行异常: {e}")
            raise
        return str(output)




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
def send_command_and_get_output(hostname: str, device_type: str, username: str, 
                              password: str, port: int = 22, command: str = "",
                              protocol: str = "ssh") -> str:
    """
    Tool that sends a command to a network device and returns its output.

    Args:
        hostname: The IP address or hostname of the device
        device_type: The type of device (e.g. cisco_ios, juniper_junos)
        username: Login username
        password: Login password
        port: Port number (default: 22 for SSH, 23 for Telnet)
        command: The command to execute on the device
        protocol: Connection protocol, either "ssh" or "telnet" (default: "ssh")

    Returns:
        The output from the executed command as a string

    ## Note
    - Acceptable commands depend on the device_type of the network device. 
      You should carefully generate appropriate commands for the device_type.
    - For Telnet connections, device_type should end with "_telnet" (e.g. cisco_ios_telnet)
    """
    if secured_mode:
        for prefix in destructive_command_prefixes:
            if command.startswith(prefix):
                logger.warning(f"block destructive command for {hostname}: {command}")
                return f"Error: destructive command '{command}' is prohibited."

    try:
        # 修改device_type以支持telnet
        if protocol.lower() == "telnet":
            # 对于 H3C 设备使用 hp_comware_telnet
            if "h3c" in device_type.lower() or "hp" in device_type.lower():
                device_type = "hp_comware_telnet"
            elif not device_type.endswith("_telnet"):
                device_type = f"{device_type}_telnet"
            
            if port == 22:  # 如果未指定端口，对telnet使用默认端口23
                port = 23

        logger.info(f"Connecting to {hostname}:{port} via {protocol} with device_type: {device_type}")
        device = Device(hostname=hostname, 
                       device_type=device_type,
                       username=username,
                       password=password,
                       port=port)
        
        logger.info(f"Sending command to {hostname}:{port} via {protocol} {command}")
        ret = device.send_command(command)
        logger.info(f"Command executed successfully, output length: {len(ret)}")
    except exceptions.ConnectionException as e:
        ret = f"Connection Error: {e}"
    except ValueError as e:
        ret = f"Configuration Error: {e}"

    return ret

# @mcp.tool()
# def get_network_device_list() -> str:
#     """
#     List all network devices that are controllable through this netmiko MCP server.

#     This tool returns a list of objects representing network devices, including:
#     - name: The name of the device
#     - hostname: The IP address or hostname (domain name) of the device
#     - device_type: The type (vendor and/or model) of this devie

#     ## Example response structure:
#     ```json
#     [
#         {
#             "name": "nexus1",
#             "hostname": 172.16.0.1,
#             "device_type": "cisco_nexus"
#         },
#         {
#             "name": "router1",
#             "hostname": 172.16.0.2,
#             "device_type": "juniper_junos"
#         },
#     ]
#     ```

#     ## How to use this information:
#     1. Use `name` to specify a network device to control via other tools that this netmiko MCP server provides.
#     2. Consider `device_type` to generate operational commands and configation commands depending on e.g., vendor, product, and operating systems.
#     3. When displaying the list of the controllable network devices, putting the list in a table format would be better, if the user does not specify display formats.

#     """

#     logger.info("resource device list!!")
#     devs = load_config_toml()
#     return json.dumps([ dev.json() for dev in devs.values() ])


# @mcp.tool()
# def send_command_and_get_output(name: str, command: str) -> str:
#     """

#     Tool that sends a command to a network device specified by the name and returns its output.

#     You can get available network devices via tool "get_network_device_list".

#     ## Note
#     - Acceptalbe commands depend on the device_type of the network device you specified. You should carefully generate appropriate commands for the device_type.

#     """
#     if secured_mode:
#         for prefix in destructive_command_prefixes:
#             if command.startswith(prefix):
#                 logger.warning(f"block destructive command for {name}: {command}")
#                 return f"Error: destructive command '{command}' is prohibited."

#     devs = load_config_toml()

#     if not name in devs:
#         ret = f"Error: no device named '{name}'"
#         logger.warning(f"get_output: {ret}")
#         return ret

#     try:
#         ret = devs[name].send_command(command)
#     except exceptions.ConnectionException as e:
#         ret = f"Connection Error: {e}"

#     logger.info(f"get: name={name} command='{command}' ret='{ret[:100]} ...'")

#     return ret


# @mcp.tool()
# def set_config_commands_and_commit_or_save(name: str, commands: list[str]) -> str:

#     """Tool that sends a series of configuration commands to a network device specified by the name.

#     You can get available network devices via tool "get_network_device_list".

#     ## Note
#     - Acceptable configuration commands depdend on the device_type of the device you specified. You should carefully generate appropriate configuration commands for the device_type.
#     - After sending the commands, this tool automatically calls commit and save if necessary, and it returns their output.
#     """

#     if disable_config:
#         return "changing configuration is prohibited"

#     devs = load_config_toml()
#     if not name in devs:
#         ret = f"Error: no device named '{name}'"
#         logger.warning(f"get_output: {ret}")
#         return ret

#     try:
#         ret = devs[name].send_config_set_and_commit_and_save(commands)

#     except exceptions.ConnectionException as e:
#         ret = f"Connection Error: {e}"

#     logger.info(f"set: name={name} command='{commands}' ret='{ret[:100]} ...'")

#     return ret

def create_app(debug: bool = False):
    """创建 Starlette 应用实例的工厂函数"""
    return Starlette(
        debug=debug,
        routes=[
            Mount("/", app=mcp.sse_app())
        ]
    )

def main():

    desc = "mcp-netmiko-server"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--disable-config", action="store_true",
                        help="disable chaning configuration")
    parser.add_argument("--secured", action="store_true",
                        help=("prohibit destructive commands, "
                              "'clear', 'request', etc, from being executed"))
    parser.add_argument("--sse", action="store_true",
                        help="run as an SSE server (default stdio)")
    parser.add_argument("--port", type=int, default = 10000,
                        help="port number for SSE server")
    parser.add_argument("--bind", type=str, default = "127.0.0.1",
                        help="bind address for SSE server")
    parser.add_argument("--debug", action="store_true",
                        help="enable starlette debug mode for SSE server")

    # parser.add_argument("tomlpath", help = "path to config toml file")

    args = parser.parse_args()

    # global tomlpath
    # tomlpath = args.tomlpath

    global disable_config
    disable_config = args.disable_config

    global secured_mode
    secured_mode = args.secured

    # make sure the current config toml is valid
    # load_config_toml()

    if args.sse:
        # 将应用定义移到全局作用域
        import uvicorn
        uvicorn.run(
            "main:create_app",  # 使用导入字符串
            host=args.bind, 
            port=args.port,
            reload=True,           # 启用热重载
            reload_dirs=["."],     # 监视当前目录的文件变化
            log_level="info",      # 设置日志级别
            factory=True           # 指示 create_app 是一个工厂函数
        )

    else:
        mcp.run()


if __name__ == "__main__":
    main()
