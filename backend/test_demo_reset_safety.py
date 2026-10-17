import os
import sqlite3
import pytest
from seed_walkthrough_patient import reset_events, EMAIL

@pytest.fixture
def mock_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT)")
    cursor.execute("CREATE TABLE patients (id INTEGER PRIMARY KEY, user_id INTEGER, timezone TEXT)")
    cursor.execute("CREATE TABLE medication_events (id INTEGER PRIMARY KEY, patient_id INTEGER, status TEXT)")

    # 1. Real patient
    cursor.execute("INSERT INTO users VALUES (1, 'real_patient@hospital.org', 'Real Clinical Patient')")
    cursor.execute("INSERT INTO patients VALUES (101, 1, 'UTC')")
    cursor.execute("INSERT INTO medication_events VALUES (1, 101, 'TAKEN')")
    cursor.execute("INSERT INTO medication_events VALUES (2, 101, 'MISSED')")

    # 2. Synthetic demo patient
    cursor.execute("INSERT INTO users VALUES (2, ?, 'Flutter Walkthrough Patient')", (EMAIL,))
    cursor.execute("INSERT INTO patients VALUES (102, 2, 'UTC')")
    cursor.execute("INSERT INTO medication_events VALUES (3, 102, 'SKIPPED')")

    conn.commit()
    yield cursor
    conn.close()

def test_reset_events_blocks_real_patient(mock_db):
    """Proves that calling reset_events on any real patient raises a PermissionError and deletes zero rows."""
    with pytest.raises(PermissionError) as exc_info:
        reset_events(mock_db, patient_id=101)
    
    assert "CLINICAL SAFETY VIOLATION" in str(exc_info.value)
    
    # Verify no events were touched for real patient 101
    count = mock_db.execute("SELECT count(*) FROM medication_events WHERE patient_id = 101").fetchone()[0]
    assert count == 2

def test_reset_events_blocks_nonexistent_patient(mock_db):
    """Proves that calling reset_events on a non-existent patient raises a PermissionError."""
    with pytest.raises(PermissionError) as exc_info:
        reset_events(mock_db, patient_id=999)
    
    assert "CLINICAL SAFETY VIOLATION" in str(exc_info.value)

def test_reset_events_blocks_production_and_unauthorized_environments(mock_db, monkeypatch):
    """Proves that calling reset_events fails closed when ENVIRONMENT is production, staging, or unset."""
    for bad_env in ["production", "staging", "uat", "", None]:
        if bad_env is None:
            monkeypatch.delenv("ENVIRONMENT", raising=False)
        else:
            monkeypatch.setenv("ENVIRONMENT", bad_env)
        
        with pytest.raises(PermissionError) as exc_info:
            reset_events(mock_db, patient_id=102)
        
        assert "strictly fail-closed" in str(exc_info.value)

def test_reset_events_allows_synthetic_demo_patient_in_dev_and_test(mock_db, monkeypatch):
    """Proves that synthetic demo patient 102 can only be reset in development or test."""
    for valid_env in ["development", "test", "demo"]:
        monkeypatch.setenv("ENVIRONMENT", valid_env)
        
        # Insert a dummy event so there's something to delete
        mock_db.execute("INSERT OR REPLACE INTO medication_events VALUES (3, 102, 'SKIPPED')")
        reset_events(mock_db, patient_id=102)
        
        # Synthetic events deleted
        count = mock_db.execute("SELECT count(*) FROM medication_events WHERE patient_id = 102").fetchone()[0]
        assert count == 0
        
        # Real patient events still 100% untouched
        real_count = mock_db.execute("SELECT count(*) FROM medication_events WHERE patient_id = 101").fetchone()[0]
        assert real_count == 2
