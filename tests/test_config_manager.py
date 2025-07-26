import pytest
import os
from services.config_manager import ConfigManager

@pytest.fixture
def setup_config_file(tmp_path):
    config_content = """
[COMMUNITY_ODOO]
url = http://localhost:8069
db = test_community_db
username = test_community_user
password = test_community_pass

[ONLINE_ODOO]
url = https://test.odoo.com
db = test_online_db
username = test_online_user
password = test_online_pass
"""
    config_path = tmp_path / "config.ini"
    config_path.write_text(config_content)
    return str(config_path)

def test_get_community_credentials(setup_config_file):
    config_manager = ConfigManager(config_file=setup_config_file)
    creds = config_manager.get_community_credentials()
    assert creds['url'] == 'http://localhost:8069'
    assert creds['db'] == 'test_community_db'
    assert creds['username'] == 'test_community_user'
    assert creds['password'] == 'test_community_pass'

def test_get_online_credentials(setup_config_file):
    config_manager = ConfigManager(config_file=setup_config_file)
    creds = config_manager.get_online_credentials()
    assert creds['url'] == 'https://test.odoo.com'
    assert creds['db'] == 'test_online_db'
    assert creds['username'] == 'test_online_user'
    assert creds['password'] == 'test_online_pass'

def test_missing_section_raises_error(tmp_path):
    config_content = """
[COMMUNITY_ODOO]
url = http://localhost:8069
"""
    config_path = tmp_path / "config.ini"
    config_path.write_text(config_content)
    config_manager = ConfigManager(config_file=str(config_path))
    with pytest.raises(ValueError, match="Section 'ONLINE_ODOO' not found in config.ini"):
        config_manager.get_online_credentials()

def test_missing_key_raises_error(tmp_path):
    config_content = """
[COMMUNITY_ODOO]
url = http://localhost:8069
db = test_community_db
username = test_community_user

[ONLINE_ODOO]
url = https://test.odoo.com
db = test_online_db
username = test_online_user
password = test_online_pass
"""
    config_path = tmp_path / "config.ini"
    config_path.write_text(config_content)
    config_manager = ConfigManager(config_file=str(config_path))
    with pytest.raises(ValueError, match="Key 'password' not found in section 'COMMUNITY_ODOO'"):
        config_manager.get_community_credentials()
