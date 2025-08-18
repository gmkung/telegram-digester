"""
Storage system for cursors and data persistence
"""
import json
import os
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict


logger = logging.getLogger(__name__)


@dataclass
class DigestRun:
    """Record of a digest generation run"""
    timestamp: str
    message_count: int
    chat_count: int
    success: bool
    error_message: Optional[str] = None
    llm_provider: Optional[Dict[str, str]] = None
    processing_time_seconds: Optional[float] = None


class StorageManager:
    """Manage persistent storage for the bot"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        storage_config = config.get('storage', {})
        self.data_dir = Path(storage_config.get('data_directory', './data'))
        self.backup_days = storage_config.get('backup_days', 30)
        
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.cursors_file = self.data_dir / 'cursors.json'
        self.history_file = self.data_dir / 'digest_history.json'
        self.last_digest_file = self.data_dir / 'last_digest.json'
        self.backup_dir = self.data_dir / 'backups'
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized storage manager with data directory: {self.data_dir}")
    
    def load_cursors(self) -> Dict[str, int]:
        """Load message cursors from storage"""
        try:
            if self.cursors_file.exists():
                with open(self.cursors_file, 'r') as f:
                    cursors = json.load(f)
                logger.info(f"Loaded cursors for {len(cursors)} chats")
                return cursors
            else:
                logger.info("No existing cursors found, starting fresh")
                return {}
        except Exception as e:
            logger.error(f"Failed to load cursors: {e}")
            return {}
    
    def save_cursors(self, cursors: Dict[str, int]) -> bool:
        """Save message cursors to storage"""
        try:
            # Create backup of existing cursors
            if self.cursors_file.exists():
                backup_path = self.backup_dir / f"cursors_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                shutil.copy2(self.cursors_file, backup_path)
            
            # Save new cursors
            with open(self.cursors_file, 'w') as f:
                json.dump(cursors, f, indent=2)
            
            logger.info(f"Saved cursors for {len(cursors)} chats")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save cursors: {e}")
            return False
    
    def load_digest_history(self) -> List[DigestRun]:
        """Load digest run history"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                
                history = []
                for item in data:
                    history.append(DigestRun(**item))
                
                logger.info(f"Loaded {len(history)} digest history records")
                return history
            else:
                logger.info("No digest history found")
                return []
                
        except Exception as e:
            logger.error(f"Failed to load digest history: {e}")
            return []
    
    def save_digest_run(self, digest_run: DigestRun) -> bool:
        """Save a digest run record to history"""
        try:
            # Load existing history
            history = self.load_digest_history()
            
            # Add new run
            history.append(digest_run)
            
            # Keep only recent history (last 100 runs)
            history = history[-100:]
            
            # Save updated history
            with open(self.history_file, 'w') as f:
                json.dump([asdict(run) for run in history], f, indent=2, default=str)
            
            logger.info("Saved digest run to history")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save digest run: {e}")
            return False
    
    def save_last_digest(self, digest_data: Dict[str, Any]) -> bool:
        """Save the most recent digest data"""
        try:
            with open(self.last_digest_file, 'w') as f:
                json.dump(digest_data, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info("Saved last digest data")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save last digest: {e}")
            return False
    
    def load_last_digest(self) -> Optional[Dict[str, Any]]:
        """Load the most recent digest data"""
        try:
            if self.last_digest_file.exists():
                with open(self.last_digest_file, 'r') as f:
                    data = json.load(f)
                logger.info("Loaded last digest data")
                return data
            else:
                logger.info("No previous digest found")
                return None
                
        except Exception as e:
            logger.error(f"Failed to load last digest: {e}")
            return None
    
    def get_last_run_time(self) -> Optional[datetime]:
        """Get the timestamp of the last successful digest run"""
        try:
            history = self.load_digest_history()
            if not history:
                return None
            
            # Find the last successful run
            for run in reversed(history):
                if run.success:
                    return datetime.fromisoformat(run.timestamp)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get last run time: {e}")
            return None
    
    def cleanup_old_backups(self) -> bool:
        """Clean up old backup files"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.backup_days)
            
            removed_count = 0
            for backup_file in self.backup_dir.glob("*"):
                if backup_file.is_file():
                    # Extract timestamp from filename
                    try:
                        if "_backup_" in backup_file.name:
                            timestamp_str = backup_file.name.split("_backup_")[1].split(".")[0]
                            file_date = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                            
                            if file_date < cutoff_date:
                                backup_file.unlink()
                                removed_count += 1
                    except (ValueError, IndexError):
                        # Skip files with unexpected naming format
                        continue
            
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} old backup files")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {e}")
            return False
    
    def export_digest_json(self, digest_data: Dict[str, Any], filename: Optional[str] = None) -> str:
        """Export digest data as JSON file"""
        try:
            if not filename:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"digest_{timestamp}.json"
            
            export_path = self.data_dir / filename
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(digest_data, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"Exported digest to {export_path}")
            return str(export_path)
            
        except Exception as e:
            logger.error(f"Failed to export digest JSON: {e}")
            raise
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get statistics about stored data"""
        try:
            stats = {
                "data_directory": str(self.data_dir),
                "cursors_exist": self.cursors_file.exists(),
                "history_exist": self.history_file.exists(),
                "last_digest_exist": self.last_digest_file.exists(),
                "backup_count": len(list(self.backup_dir.glob("*"))),
                "directory_size_mb": 0
            }
            
            # Calculate directory size
            total_size = 0
            for path in self.data_dir.rglob("*"):
                if path.is_file():
                    total_size += path.stat().st_size
            
            stats["directory_size_mb"] = round(total_size / (1024 * 1024), 2)
            
            # Get cursor count
            cursors = self.load_cursors()
            stats["cursor_count"] = len(cursors)
            
            # Get history count
            history = self.load_digest_history()
            stats["history_count"] = len(history)
            
            # Last run info
            last_run = self.get_last_run_time()
            if last_run:
                stats["last_successful_run"] = last_run.isoformat()
                stats["hours_since_last_run"] = (datetime.now() - last_run).total_seconds() / 3600
            else:
                stats["last_successful_run"] = None
                stats["hours_since_last_run"] = None
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {"error": str(e)}
    
    def reset_cursors(self, chat_identifiers: Optional[List[str]] = None) -> bool:
        """Reset cursors for specified chats or all chats"""
        try:
            cursors = self.load_cursors()
            
            if chat_identifiers:
                # Reset only specified chats
                for chat_id in chat_identifiers:
                    if chat_id in cursors:
                        cursors[chat_id] = 0
                        logger.info(f"Reset cursor for {chat_id}")
            else:
                # Reset all cursors
                cursors = {}
                logger.info("Reset all cursors")
            
            return self.save_cursors(cursors)
            
        except Exception as e:
            logger.error(f"Failed to reset cursors: {e}")
            return False
    
    def backup_all_data(self) -> str:
        """Create a backup of all data files"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"full_backup_{timestamp}"
            backup_path = self.backup_dir / backup_name
            backup_path.mkdir()
            
            # Copy all data files
            files_copied = 0
            for data_file in self.data_dir.glob("*.json"):
                if data_file.is_file() and data_file.parent == self.data_dir:
                    shutil.copy2(data_file, backup_path / data_file.name)
                    files_copied += 1
            
            logger.info(f"Created full backup with {files_copied} files at {backup_path}")
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            raise