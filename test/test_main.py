
import os
import pytest

from main import Device, load_config_toml

script_dir = os.path.dirname(__file__)


# Test instantiating Device
device_valid_params = [
    {
        "name": "test", "hostname": "localhost", "device_type": "linux"
    },
    {
        "name": "test", "hostname": "juniper", "device_type": "juniper_junos"
    },
    {
        "name": "test", "hostname": "cisco", "device_type": "cisco_xr", "port": 2022,
    },
]
@pytest.mark.parametrize("param", device_valid_params)
def test_device_valid(param):
    Device(**param)


# Test instantiating Device will fail
device_invalid_params = [
    {
        "name": "test", "hostname": "localhost", "device_type": "unknown"
    },
]
@pytest.mark.parametrize("param", device_invalid_params)
def test_device_invalid(param):
    with pytest.raises(ValueError):
        Device(**param)


# Test load toml config file
def test_load_toml():
    devs = load_config_toml(os.path.join(script_dir, "sample.toml"))
    assert devs["linux1"].username == "linuxuser"
    assert devs["qfx1"].device_type == "juniper_junos"
    assert devs["qfx1"].username == "rouser"

    
