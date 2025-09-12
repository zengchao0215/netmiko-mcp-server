import argparse
from netmiko import ConnectHandler
from netmiko import exceptions
from netmiko.ssh_dispatcher import platforms, telnet_platforms
from winrm.protocol import Protocol
from pyghmi.ipmi import command as ipmi_command
import json

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
                              password: str, port: int = None, command: str = None,
                              protocol: str = "ssh") -> str:
    """
    Tool that sends a command to a network device or os device and returns its output.

    Args:
        hostname: The IP address or hostname of the device
        device_type: The device_type must strictly follow the types officially supported by netmiko， (e.g. cisco_ios, juniper_junos, ruijie_os)，
        username: Login username
        password: Login password
        port: Port number (default: 22 for SSH, 23 for Telnet， 5985 for WinRM)
        command: The command to execute on the device
        protocol: Connection protocol, either "ssh"、"telnet"、"winrm"、"ipmi" (default: "ssh")

    Returns:
        The output from the executed command as a string

    ## Note
    - Acceptable commands depend on the device_type of the network device. 
      You should carefully generate appropriate commands for the device_type.
    - For Telnet connections, device_type should end with "_telnet" (e.g. cisco_ios_telnet)
    - 对于 ipmi 协议，command 参数必须为 JSON 字符串，格式如下：
        {
            "netfn": <int>,
            "command": <int>,
            "data": [<int>, ...]   # 可选，默认为空数组
        }
      示例：
        '{"netfn": 0x06, "command": 0x01, "data": [0x00, 0x01]}'
      如果 command 不是合法的 JSON 字符串，将返回错误："Error: command is not a valid JSON string."
    """
    protocol = protocol.lower()
    if protocol not in ["ssh", "telnet"]:
        return f"Error: unsupported protocol '{protocol}'. Supported protocols are 'ssh', 'telnet'"
    
    if secured_mode:
        for prefix in destructive_command_prefixes:
            if command.startswith(prefix):
                logger.warning(f"block destructive command for {hostname}: {command}")
                return f"Error: destructive command '{command}' is prohibited."

    try:
        if port is None:
            port = 22
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

@mcp.tool()
def send_winrm_command_and_get_output(hostname: str, username: str, 
                              password: str, command: str,
                              transport: str = "ntlm",
                              port: int = 5985,
                              protocol: str = "http") -> str:
    """
    Tool that sends a command to a windows device and returns its output.

    Args:
        hostname: The IP address or hostname of the device
        username: Login username
        password: Login password
        command: The command to execute on the device
        transport: The transport must strictly follow the types officially supported by winrm， (e.g. basic, ntlm, kerberos, negotiate, certificate)，default ntlm
        port: Port number (default: 5985 for WinRM)
        protocol: Connection protocol, either "http"、"https" (default: "http")

    Returns:
        The output from the executed command as a string

    """
    protocol = protocol.lower()
    if protocol not in ["http", "https"]:
        return f"Error: unsupported protocol '{protocol}'. Supported protocols are 'http', 'https'."
    transport = transport.lower()
    if transport not in ["basic", "ntlm", "kerberos", "negotiate", "certificate"]:
        transport = "ntlm"

    if port is None:
        port = protocol == "http" and 5985 or 5986

    try: 
        winrm_url = f"{protocol}://{hostname}:{port}/wsman"
        # print("winrm_url = ", winrm_url, username, transport)
        # winrmSession = winrm.Session("172.17.189.125", auth=(r".\administrator", "VMware1!"), transport="ntlm")
        # result = winrmSession.run_cmd("ipconfig", ["/all"])
        # winrmSession = winrm.Session(hostname, auth=(username, password), transport=transport)
        # result = winrmSession.run_cmd(command)

        p = Protocol(
            endpoint=winrm_url,
            transport=transport,
            username=username,
            password=password,
            server_cert_validation='ignore')
        shell_id = p.open_shell()
        command_id = p.run_command(shell_id, command)
        std_out, std_err, status_code = p.get_command_output(shell_id, command_id)
        
        if status_code != 0:
            ret = f"Command Error: {std_err.decode('utf-8')}"
        else:
            ret = std_out.decode('utf-8')
        p.cleanup_command(shell_id, command_id)
        p.close_shell(shell_id)
    except Exception as e:
        ret = f"Connection Error: {e}"
            
    return ret

@mcp.tool()
def send_ipmi_command_and_get_output(hostname: str, username: str, 
                              password: str, port: int = 623, command: str = None) -> str:
    """
    Tool that sends a command to a windows device and returns its output.

    Args:
        hostname: The IP address or hostname of the device
        username: Login username
        password: Login password
        port: Port number (default: 623 for ipmi)
        command: The command to execute on the device

    Returns:
        The output from the executed command as a string

    ## Note
    - 对于 ipmi 协议，command 参数必须为 JSON 字符串，格式如下：
        {
            "netfn": <int>,
            "command": <int>,
            "data": [<int>, ...]   # 可选，默认为空数组
        }
      其中的netfn/command均为整数, data为整数数组，且数值需要遵循IPMI协议规范以及ipmitool_raw的参数要求
      示例：
        '{"netfn": 6, "command": 1, "data": [0, 1]}'
      如果 command 不是合法的 JSON 字符串，将返回错误："Error: command is not a valid JSON string."
    """
    try:
        bmc = json.loads(command)
    except Exception:
        return "Error: command is not a valid JSON string."
    try:
        ipmi_cmd = ipmi_command.Command(bmc=hostname, userid=username, password=password, port=port)
        print("ipmi_cmd: ", ipmi_cmd)
        response = ipmi_cmd.raw_command(netfn=bmc.get("netfn"), command=bmc.get("command"), data=bmc.get("data", []))
        ret = str(response)
    except Exception as e:
        ret = f"Connection Error: {e}"

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
