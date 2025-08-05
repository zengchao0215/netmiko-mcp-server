
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