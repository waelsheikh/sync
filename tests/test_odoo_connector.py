import pytest
from services.odoo_connector import OdooConnector
from odoorpc.exceptions import Error as OdooError
import logging

@pytest.fixture
def mock_odoorpc(mocker):
    # Mock the odoorpc.Client class
    mock_client = mocker.patch('odoorpc.Client')
    # Configure the mock client to return a mock API object
    mock_api = mocker.Mock()
    mock_api.env = {'ir.model.fields': mocker.Mock(), 'ir.model': mocker.Mock()}
    mock_api.env['ir.model.fields'].search.return_value = [] # Field does not exist by default
    mock_api.env['ir.model'].search.return_value = [1] # Mock model ID
    mock_api.version = {'server_serie': '16.0'}
    mock_client.return_value = mock_api
    return mock_client

@pytest.fixture
def mock_logger(mocker):
    return mocker.Mock(spec=logging.Logger)

@pytest.fixture
def credentials():
    return {
        'url': 'http://localhost:8069',
        'db': 'test_db',
        'username': 'test_user',
        'password': 'test_pass'
    }

def test_odoo_connector_connect_success(mock_odoorpc, credentials, mock_logger):
    connector = OdooConnector(credentials, logger=mock_logger)
    mock_odoorpc.assert_called_once_with(
        credentials['url'].split('//')[1].split(':')[0],
        credentials['db'],
        credentials['username'],
        credentials['password'],
        protocol='json-rpc',
        port=8069
    )
    mock_logger.info.assert_called_with(f"تم الاتصال وتسجيل الدخول بنجاح إلى Odoo في '{credentials['url']}' (قاعدة البيانات: {credentials['db']})")

def test_odoo_connector_connect_failure(mock_odoorpc, credentials, mock_logger):
    mock_odoorpc.side_effect = OdooError('Authentication failed')
    with pytest.raises(ConnectionError, match="فشل الاتصال بـ Odoo: Authentication failed"):
        OdooConnector(credentials, logger=mock_logger)
    mock_logger.error.assert_any_call("خطأ في تسجيل الدخول إلى Odoo: Authentication failed")

def test_ensure_custom_field_creates_field(mock_odoorpc, credentials, mock_logger):
    connector = OdooConnector(credentials, logger=mock_logger)
    model_name = 'res.partner'
    field_name = 'x_test_field'
    field_label = 'Test Field'
    field_type = 'char'

    connector.ensure_custom_field(model_name, field_name, field_label, field_type, logger=mock_logger)

    mock_odoorpc.return_value.env['ir.model.fields'].search.assert_called_with([
        ('model', '=', model_name),
        ('name', '=', field_name)
    ])
    mock_odoorpc.return_value.env['ir.model.fields'].create.assert_called_once()
    mock_logger.info.assert_any_call(f"  - الحقل '{field_name}' غير موجود في النموذج '{model_name}'. جاري الإنشاء...")
    mock_logger.info.assert_any_call(f"  - تم إنشاء الحقل '{field_name}' بنجاح في النموذج '{model_name}'.")

def test_ensure_custom_field_field_exists(mock_odoorpc, credentials, mock_logger):
    connector = OdooConnector(credentials, logger=mock_logger)
    model_name = 'res.partner'
    field_name = 'x_existing_field'
    field_label = 'Existing Field'
    field_type = 'char'

    mock_odoorpc.return_value.env['ir.model.fields'].search.return_value = [1] # Simulate field exists

    connector.ensure_custom_field(model_name, field_name, field_label, field_type, logger=mock_logger)

    mock_odoorpc.return_value.env['ir.model.fields'].create.assert_not_called()
    mock_logger.info.assert_any_call(f"  - الحقل '{field_name}' موجود بالفعل في النموذج '{model_name}'.")

def test_get_api_reconnects_if_needed(mock_odoorpc, credentials, mock_logger):
    connector = OdooConnector(credentials, logger=mock_logger)
    # Simulate API disconnection
    connector.api.uid = None
    
    connector.get_api()
    mock_odoorpc.assert_called_with(
        credentials['url'].split('//')[1].split(':')[0],
        credentials['db'],
        credentials['username'],
        credentials['password'],
        protocol='json-rpc',
        port=8069
    )
    mock_logger.warning.assert_called_with("الاتصال غير قائم. محاولة إعادة الاتصال...")
