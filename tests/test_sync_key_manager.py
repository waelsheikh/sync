import pytest
import os
import sqlite3
from services.sync_key_manager import SyncKeyManager

@pytest.fixture
def setup_key_manager():
    db_file = 'test_sync_map.db'
    if os.path.exists(db_file):
        os.remove(db_file)
    manager = SyncKeyManager(db_file)
    yield manager
    manager.close_connection()
    if os.path.exists(db_file):
        os.remove(db_file)

def test_add_and_get_mapping(setup_key_manager):
    manager = setup_key_manager
    manager.add_mapping('res.partner', 1, 101)
    assert manager.get_destination_id('res.partner', 1) == 101

def test_update_mapping(setup_key_manager):
    manager = setup_key_manager
    manager.add_mapping('res.partner', 1, 101)
    manager.add_mapping('res.partner', 1, 102) # Update
    assert manager.get_destination_id('res.partner', 1) == 102

def test_get_non_existent_mapping(setup_key_manager):
    manager = setup_key_manager
    assert manager.get_destination_id('res.partner', 999) is None

def test_get_all_source_ids_for_model(setup_key_manager):
    manager = setup_key_manager
    manager.add_mapping('res.partner', 1, 101)
    manager.add_mapping('res.partner', 2, 102)
    manager.add_mapping('account.move', 1, 201)
    source_ids = manager.get_all_source_ids_for_model('res.partner')
    assert sorted(source_ids) == [1, 2]
    source_ids_move = manager.get_all_source_ids_for_model('account.move')
    assert source_ids_move == [1]
    source_ids_non_existent = manager.get_all_source_ids_for_model('non.existent.model')
    assert source_ids_non_existent == []

def test_remove_mapping(setup_key_manager):
    manager = setup_key_manager
    manager.add_mapping('res.partner', 1, 101)
    manager.remove_mapping('res.partner', 1)
    assert manager.get_destination_id('res.partner', 1) is None

def test_remove_non_existent_mapping(setup_key_manager):
    manager = setup_key_manager
    manager.remove_mapping('res.partner', 999) # Should not raise an error
    assert manager.get_destination_id('res.partner', 999) is None
