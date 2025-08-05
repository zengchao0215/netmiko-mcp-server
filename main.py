import argparse

from netmiko import ConnectHandler
from netmiko import exceptions
from netmiko.ssh_dispatcher import platforms, telnet_platforms

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount

import logging
logger = logging.getLogger("mcp-netmiko-server")
logging.basicConfig(level=logging.INFO)

#是否开启安全模式，禁止执行破坏性命令
secured_mode: bool = False
#是否开启调试模式，打印更多日志
debug_mode: bool = False

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
            "session_log": f"logs/netmiko_session_{self.hostname}.log",  # 用于调试连接问题
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

    args = parser.parse_args()

    global secured_mode
    secured_mode = args.secured

    global debug_mode
    debug_mode = args.debug

    if args.sse:
        # 将应用定义移到全局作用域
        import uvicorn
        uvicorn.run(
            "main:create_app",  # 使用导入字符串
            host=args.bind, 
            port=args.port,
            reload=debug_mode,           # 启用热重载
            reload_dirs=["."],     # 监视当前目录的文件变化
            log_level="info",      # 设置日志级别
            factory=True           # 指示 create_app 是一个工厂函数
        )

    else:
        mcp.run()


if __name__ == "__main__":
    main()
