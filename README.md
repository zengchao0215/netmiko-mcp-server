
# mcp-netmiko-server

An MCP server that enables LLMs interacting with your network devices
 via SSH (netmiko).

| Tool                                   | Description                                                               |
|:---------------------------------------|:--------------------------------------------------------------------------|
| send_command_and_get_output            | Send a command to a device and returns its output.                        |


## How to use

* Install

```console
https://github.com/zengchao0215/netmiko-mcp-server.git
cd netmiko-mcp-server

# 创建名为venv的虚拟环境
python -m venv venv    

# Mac/Linux激活            
source venv/bin/activate   

# Windows激活       
venv\Scripts\activate              

# 批量安装依赖
pip install -r requirements.txt    

# 启动sse服务
python main.py --bind 0.0.0.0 --port 10000 --sse

# 启动sse服务，并开启安全模式
python main.py --bind 0.0.0.0 --port 10000 --sse --secured

# 启动sse服务，并开启Debug模式
python main.py --bind 0.0.0.0 --port 10000 --sse --debug

## device_type 说明（严格遵循 netmiko 标准）

- device_type 参数必须严格按照 netmiko 官方支持的类型填写，详见 netmiko/ssh_dispatcher.py 文件中的 platforms 和 telnet_platforms 列表，或参考 [netmiko 官方文档](https://ktbyers.github.io/netmiko/docs/netmiko/index.html#supported-platforms)。
- 不同厂商和设备类型有不同的 device_type 名称，拼写需完全一致（区分大小写）。
- 常见 device_type 示例：
  - cisco_ios
  - cisco_xe
  - cisco_nxos
  - huawei
  - juniper
  - hp_comware
  - arista_eos
  - ...（详见 netmiko 支持列表）

- Telnet 设备需以 `_telnet` 结尾，如 `cisco_ios_telnet`。

- 如需获取完整 device_type 列表，可直接查看本项目 `netmiko/ssh_dispatcher.py` 文件中的 `platforms` 和 `telnet_platforms` 变量，或运行如下 Python 代码获取：
  ```python
  from netmiko.ssh_dispatcher import platforms, telnet_platforms
  print("SSH 支持：", platforms)
  print("Telnet 支持：", telnet_platforms)
  ```
