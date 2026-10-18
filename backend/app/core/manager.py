"""Manager for the active data source."""
from typing import Optional, List
from backend.app.core.interfaces import BaseDataSource
from backend.app.core.models import ConnectionInfo


class DataSourceManager:
    """Manages the active connection and the connection history."""

    def __init__(self):
        self._active_source: Optional[BaseDataSource] = None
        self._recent_paths: List[str] = []

    def set_active_source(self, source: BaseDataSource) -> None:
        """Set the active data source, closing the previous one if it existed."""
        if self._active_source and self._active_source.is_connected():
            try:
                self._active_source.close()
            except Exception:
                pass
        self._active_source = source
        info = source.get_connection_info()
        if info.path and info.path not in self._recent_paths:
            self._recent_paths.insert(0, info.path)
            # Keep at most 10 recent paths
            self._recent_paths = self._recent_paths[:10]

    def get_active_source(self) -> BaseDataSource:
        """Return the active source or raise an error if there is no connection."""
        if not self._active_source or not self._active_source.is_connected():
            raise RuntimeError("No database is connected.")
        return self._active_source

    def is_connected(self) -> bool:
        """Check whether there is an active connection."""
        return self._active_source is not None and self._active_source.is_connected()

    def get_connection_info(self) -> ConnectionInfo:
        """Get the current connection information."""
        if not self._active_source or not self._active_source.is_connected():
            return ConnectionInfo(path="", connected=False)
        return self._active_source.get_connection_info()

    def disconnect(self) -> None:
        """Disconnect the active source."""
        if self._active_source:
            self._active_source.close()
            self._active_source = None

    def get_recent_paths(self) -> List[str]:
        """Get the recent paths."""
        return list(self._recent_paths)


# Singleton instance of the manager
db_manager = DataSourceManager()
