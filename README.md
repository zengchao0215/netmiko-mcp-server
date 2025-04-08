
# mcp-netmiko-server

An MCP server that enables LLMs interacting with your network devices
 via SSH (netmiko).

| Tool                                   | Description                                                               |
|:---------------------------------------|:--------------------------------------------------------------------------|
| list_devices                           | Return list of network device names and types defined in a TOML file.     |
| send_command_and_get_output            | Send a command to a device and returns its output.                        |
| set_config_commands_and_commit_or_save | Send configuration commands to a device and commit or save automatically. |



<img width="740" alt="mcp-netmiko-demo" src="https://github.com/user-attachments/assets/08ea7feb-25fc-45c9-a70c-83b75c01a725" />


## How to use

* Install

```console
git clone https://github.com/upa/mcp-netmiko-server
cd mcp-netmiko-server

# Run: write your toml file that lists your devices
uv run --with mcp[cli] --with netmiko $(pwd)/main.py $(pwd)/test/sample.toml

# Develop
uv venv
uv add mcp[cli] netmiko
./main.py test/sample.toml
```

* Configuration

List your network devices in a toml file like [sample.toml](test/sample.toml):

```toml
[default]

username = "rouser"
password = "rouserpassword"


[qfx1]

hostname = "172.16.0.40"
device_type = "juniper_junos"

[nexus1]

hostname = "nexus1.lab"
device_type = "cisco_nxos"

```

`[default]` is a special section that defines the default
values. Devices inherit the default values if not defined on their
sections.


* claude desktop config json:

```json
{
  "mcpServers": {
    "netmiko server": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "mcp[cli]",
        "--with",
        "netmiko",
        "[PATH TO]/mcp-netmiko-server/main.py",
        "[PATH TO]/YOUR-DEVICE.toml"
      ]
    }
  }
}
```
