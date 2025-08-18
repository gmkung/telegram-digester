"""
Tests for storage module
"""
import pytest
import json
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from src.storage import StorageManager, DigestRun


class TestStorageManager:
    """Test StorageManager functionality"""
    
    @pytest.fixture
    def temp_storage_config(self, temp_data_dir):
        """Storage config using temporary directory"""
        return {
            "storage": {
                "data_directory": str(temp_data_dir),
                "backup_days": 7
            }
        }
    
    def test_init(self, temp_storage_config):
        """Test storage manager initialization"""
        storage = StorageManager(temp_storage_config)
        
        assert storage.data_dir.exists()
        assert storage.backup_dir.exists()
        assert storage.cursors_file.parent == storage.data_dir
        assert storage.backup_days == 7
    
    def test_load_cursors_empty(self, temp_storage_config):
        """Test loading cursors when none exist"""
        storage = StorageManager(temp_storage_config)
        
        cursors = storage.load_cursors()
        
        assert isinstance(cursors, dict)
        assert len(cursors) == 0
    
    def test_save_and_load_cursors(self, temp_storage_config):
        """Test saving and loading cursors"""
        storage = StorageManager(temp_storage_config)
        
        test_cursors = {
            "@test_channel": 12345,
            "-1001234567890": 67890,
            "another_chat": 999
        }
        
        # Save cursors
        success = storage.save_cursors(test_cursors)
        assert success == True
        
        # Load cursors
        loaded_cursors = storage.load_cursors()
        assert loaded_cursors == test_cursors
    
    def test_save_cursors_creates_backup(self, temp_storage_config):
        """Test that saving cursors creates backup of existing file"""
        storage = StorageManager(temp_storage_config)
        
        # Create initial cursors file
        initial_cursors = {"@test": 100}
        storage.save_cursors(initial_cursors)
        
        # Count backup files before
        backup_count_before = len(list(storage.backup_dir.glob("cursors_backup_*.json")))
        
        # Save new cursors (should create backup)
        new_cursors = {"@test": 200, "@new": 300}
        storage.save_cursors(new_cursors)
        
        # Check backup was created
        backup_count_after = len(list(storage.backup_dir.glob("cursors_backup_*.json")))
        assert backup_count_after == backup_count_before + 1
    
    def test_load_digest_history_empty(self, temp_storage_config):
        """Test loading digest history when none exists"""
        storage = StorageManager(temp_storage_config)
        
        history = storage.load_digest_history()
        
        assert isinstance(history, list)
        assert len(history) == 0
    
    def test_save_and_load_digest_run(self, temp_storage_config):
        """Test saving and loading digest run history"""
        storage = StorageManager(temp_storage_config)
        
        # Create test digest run
        digest_run = DigestRun(
            timestamp=datetime.now().isoformat(),
            message_count=25,
            chat_count=3,
            success=True,
            llm_provider={"provider": "openai", "model": "gpt-4.1"},
            processing_time_seconds=15.5
        )
        
        # Save digest run
        success = storage.save_digest_run(digest_run)
        assert success == True
        
        # Load history
        history = storage.load_digest_history()
        assert len(history) == 1
        assert history[0].message_count == 25
        assert history[0].chat_count == 3
        assert history[0].success == True
    
    def test_save_digest_run_limits_history(self, temp_storage_config):
        """Test that digest run history is limited to 100 entries"""
        storage = StorageManager(temp_storage_config)
        
        # Create 102 digest runs
        for i in range(102):
            digest_run = DigestRun(
                timestamp=datetime.now().isoformat(),
                message_count=i,
                chat_count=1,
                success=True
            )
            storage.save_digest_run(digest_run)
        
        # Should only keep last 100
        history = storage.load_digest_history()
        assert len(history) == 100
        
        # Should have the most recent entries (message_count >= 2)
        assert all(run.message_count >= 2 for run in history)
    
    def test_save_and_load_last_digest(self, temp_storage_config):
        """Test saving and loading last digest data"""
        storage = StorageManager(temp_storage_config)
        
        test_digest = {
            "urgent": ["Test urgent item"],
            "decisions": ["Test decision"],
            "metadata": {"count": 5},
            "generated_at": datetime.now().isoformat()
        }
        
        # Save digest
        success = storage.save_last_digest(test_digest)
        assert success == True
        
        # Load digest
        loaded_digest = storage.load_last_digest()
        assert loaded_digest["urgent"] == test_digest["urgent"]
        assert loaded_digest["decisions"] == test_digest["decisions"]
        assert loaded_digest["metadata"]["count"] == 5
    
    def test_get_last_run_time_no_history(self, temp_storage_config):
        """Test getting last run time when no history exists"""
        storage = StorageManager(temp_storage_config)
        
        last_run = storage.get_last_run_time()
        assert last_run is None
    
    def test_get_last_run_time_with_history(self, temp_storage_config):
        """Test getting last run time with history"""
        storage = StorageManager(temp_storage_config)
        
        # Create successful run
        success_time = datetime.now() - timedelta(hours=2)
        success_run = DigestRun(
            timestamp=success_time.isoformat(),
            message_count=10,
            chat_count=2,
            success=True
        )
        storage.save_digest_run(success_run)
        
        # Create failed run (more recent)
        fail_time = datetime.now() - timedelta(hours=1)
        fail_run = DigestRun(
            timestamp=fail_time.isoformat(),
            message_count=5,
            chat_count=1,
            success=False,
            error_message="Test error"
        )
        storage.save_digest_run(fail_run)
        
        # Should return the last successful run time
        last_run = storage.get_last_run_time()
        assert last_run is not None
        # Allow for small time differences in comparison
        assert abs((last_run - success_time).total_seconds()) < 1
    
    def test_cleanup_old_backups(self, temp_storage_config):
        """Test cleanup of old backup files"""
        storage = StorageManager(temp_storage_config)
        
        # Create old backup file
        old_time = datetime.now() - timedelta(days=storage.backup_days + 1)
        old_backup_name = f"cursors_backup_{old_time.strftime('%Y%m%d_%H%M%S')}.json"
        old_backup_path = storage.backup_dir / old_backup_name
        old_backup_path.write_text('{"test": 1}')
        
        # Create recent backup file
        recent_time = datetime.now() - timedelta(days=1)
        recent_backup_name = f"cursors_backup_{recent_time.strftime('%Y%m%d_%H%M%S')}.json"
        recent_backup_path = storage.backup_dir / recent_backup_name
        recent_backup_path.write_text('{"test": 2}')
        
        # Cleanup should remove old file but keep recent
        success = storage.cleanup_old_backups()
        assert success == True
        assert not old_backup_path.exists()
        assert recent_backup_path.exists()
    
    def test_export_digest_json(self, temp_storage_config):
        """Test exporting digest as JSON file"""
        storage = StorageManager(temp_storage_config)
        
        test_data = {
            "digest": {"urgent": ["Test"], "decisions": []},
            "metadata": {"count": 5},
            "timestamp": datetime.now().isoformat()
        }
        
        export_path = storage.export_digest_json(test_data, "test_export.json")
        
        assert export_path.endswith("test_export.json")
        assert Path(export_path).exists()
        
        # Verify content
        with open(export_path, 'r') as f:
            loaded_data = json.load(f)
        assert loaded_data["digest"]["urgent"] == ["Test"]
    
    def test_export_digest_json_auto_filename(self, temp_storage_config):
        """Test exporting digest with automatic filename"""
        storage = StorageManager(temp_storage_config)
        
        test_data = {"test": "data"}
        
        export_path = storage.export_digest_json(test_data)
        
        assert export_path.startswith(str(storage.data_dir))
        assert "digest_" in export_path
        assert export_path.endswith(".json")
        assert Path(export_path).exists()
    
    def test_get_storage_stats(self, temp_storage_config):
        """Test getting storage statistics"""
        storage = StorageManager(temp_storage_config)
        
        # Create some test data
        storage.save_cursors({"@test": 123})
        digest_run = DigestRun(
            timestamp=datetime.now().isoformat(),
            message_count=10,
            chat_count=2,
            success=True
        )
        storage.save_digest_run(digest_run)
        
        stats = storage.get_storage_stats()
        
        assert "data_directory" in stats
        assert stats["cursors_exist"] == True
        assert stats["history_exist"] == True
        assert stats["cursor_count"] == 1
        assert stats["history_count"] == 1
        assert stats["directory_size_mb"] >= 0
    
    def test_reset_cursors_all(self, temp_storage_config):
        """Test resetting all cursors"""
        storage = StorageManager(temp_storage_config)
        
        # Set up initial cursors
        initial_cursors = {"@test1": 100, "@test2": 200}
        storage.save_cursors(initial_cursors)
        
        # Reset all cursors
        success = storage.reset_cursors()
        assert success == True
        
        # Verify all cursors are cleared
        cursors = storage.load_cursors()
        assert len(cursors) == 0
    
    def test_reset_cursors_specific(self, temp_storage_config):
        """Test resetting specific cursors"""
        storage = StorageManager(temp_storage_config)
        
        # Set up initial cursors
        initial_cursors = {"@test1": 100, "@test2": 200, "@test3": 300}
        storage.save_cursors(initial_cursors)
        
        # Reset specific cursors
        success = storage.reset_cursors(["@test1", "@test3"])
        assert success == True
        
        # Verify specific cursors are reset, others remain
        cursors = storage.load_cursors()
        assert cursors["@test1"] == 0
        assert cursors["@test2"] == 200  # Unchanged
        assert cursors["@test3"] == 0
    
    def test_backup_all_data(self, temp_storage_config):
        """Test creating full data backup"""
        storage = StorageManager(temp_storage_config)
        
        # Create some test data files
        storage.save_cursors({"@test": 123})
        storage.save_last_digest({"test": "digest"})
        
        backup_path = storage.backup_all_data()
        
        assert backup_path.startswith(str(storage.backup_dir))
        assert "full_backup_" in backup_path
        assert Path(backup_path).exists()
        assert Path(backup_path).is_dir()
        
        # Verify backup contents
        backup_files = list(Path(backup_path).glob("*.json"))
        assert len(backup_files) >= 2  # cursors + last_digest files


class TestDigestRun:
    """Test DigestRun dataclass"""
    
    def test_create_digest_run(self):
        """Test creating a DigestRun instance"""
        run = DigestRun(
            timestamp="2024-01-15T10:30:00",
            message_count=25,
            chat_count=3,
            success=True,
            llm_provider={"provider": "openai", "model": "gpt-4.1"},
            processing_time_seconds=12.5
        )
        
        assert run.timestamp == "2024-01-15T10:30:00"
        assert run.message_count == 25
        assert run.chat_count == 3
        assert run.success == True
        assert run.llm_provider["provider"] == "openai"
        assert run.processing_time_seconds == 12.5
        assert run.error_message is None
    
    def test_create_digest_run_with_error(self):
        """Test creating a DigestRun with error"""
        run = DigestRun(
            timestamp="2024-01-15T10:30:00",
            message_count=0,
            chat_count=0,
            success=False,
            error_message="API connection failed"
        )
        
        assert run.success == False
        assert run.error_message == "API connection failed"
        assert run.llm_provider is None
        assert run.processing_time_seconds is None