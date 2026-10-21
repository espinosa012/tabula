"""Store for user-defined custom views persisted locally in views.json."""
from datetime import datetime, timezone
import json
import os
import threading
import uuid
from typing import List, Optional, Dict, Any

from backend.app.core.config import BASE_DIR, get_config
from backend.app.core.models import CustomView


class ViewsStore:
    """Thread-safe local JSON persistence for custom views."""

    def __init__(self, file_path: Optional[str] = None):
        self._custom_file_path = file_path
        self._lock = threading.Lock()

    def get_file_path(self) -> str:
        """Get the absolute path to views.json."""
        if self._custom_file_path:
            return os.path.abspath(self._custom_file_path)
        configured = get_config().get("views_file_path")
        if configured:
            if os.path.isabs(configured):
                return configured
            return os.path.join(BASE_DIR, configured)
        return os.path.join(BASE_DIR, "views.json")

    def _read_all(self) -> List[Dict[str, Any]]:
        """Read all view entries from the JSON file."""
        path = self.get_file_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                return data
            return []
        except (ValueError, OSError):
            return []

    def _write_all(self, entries: List[Dict[str, Any]]) -> None:
        """Atomically write view entries to the JSON file."""
        path = self.get_file_path()
        parent_dir = os.path.dirname(path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        temp_path = f"{path}.tmp.{os.getpid()}"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)

    def list_views(self, db_path: Optional[str] = None, all_views: bool = False) -> List[CustomView]:
        """List custom views, optionally filtered by database path."""
        with self._lock:
            entries = self._read_all()
            views = [CustomView(**entry) for entry in entries if isinstance(entry, dict) and "id" in entry]

        if all_views or not db_path:
            return views

        is_network_id = "://" in db_path or "@" in db_path
        if is_network_id:
            norm_db = db_path
            base_db = db_path
        else:
            norm_db = os.path.abspath(db_path)
            base_db = os.path.basename(norm_db)

        matched: List[CustomView] = []
        for v in views:
            if not v.db_path:
                matched.append(v)
            elif is_network_id:
                if v.db_path == db_path:
                    matched.append(v)
            else:
                if not ("://" in v.db_path or "@" in v.db_path):
                    if os.path.abspath(v.db_path) == norm_db:
                        matched.append(v)
                    elif os.path.basename(v.db_path) == base_db:
                        matched.append(v)
        return matched

    def get_view(self, view_id: str) -> Optional[CustomView]:
        """Retrieve a single view by its ID."""
        with self._lock:
            entries = self._read_all()
            for entry in entries:
                if entry.get("id") == view_id:
                    return CustomView(**entry)
        return None

    def create_view(
        self,
        name: str,
        sql: str,
        description: Optional[str] = None,
        db_path: Optional[str] = None,
    ) -> CustomView:
        """Create and persist a new custom view."""
        now_iso = datetime.now(timezone.utc).isoformat()
        view_id = f"view_{uuid.uuid4().hex[:12]}"
        if db_path:
            normalized_db = db_path if ("://" in db_path or "@" in db_path) else os.path.abspath(db_path)
        else:
            normalized_db = None

        new_view = CustomView(
            id=view_id,
            name=name.strip(),
            sql=sql.strip(),
            description=description.strip() if description else None,
            db_path=normalized_db,
            created_at=now_iso,
            updated_at=now_iso,
        )

        with self._lock:
            entries = self._read_all()
            entries.append(new_view.model_dump())
            self._write_all(entries)

        return new_view

    def update_view(
        self,
        view_id: str,
        name: Optional[str] = None,
        sql: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[CustomView]:
        """Update an existing view's metadata or SQL."""
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            entries = self._read_all()
            target_entry = None
            for entry in entries:
                if entry.get("id") == view_id:
                    target_entry = entry
                    break

            if not target_entry:
                return None

            if name is not None and name.strip():
                target_entry["name"] = name.strip()
            if sql is not None and sql.strip():
                target_entry["sql"] = sql.strip()
            if description is not None:
                target_entry["description"] = description.strip() if description.strip() else None
            target_entry["updated_at"] = now_iso

            self._write_all(entries)
            return CustomView(**target_entry)

    def delete_view(self, view_id: str) -> bool:
        """Delete a view by its ID."""
        with self._lock:
            entries = self._read_all()
            orig_len = len(entries)
            new_entries = [e for e in entries if e.get("id") != view_id]
            if len(new_entries) == orig_len:
                return False
            self._write_all(new_entries)
            return True


# Global default instance
views_store = ViewsStore()
