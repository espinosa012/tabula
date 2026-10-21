"""Abstract interfaces and contracts for data sources."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from backend.app.core.models import (
    TableSummary,
    TableSchema,
    PaginationParams,
    PaginatedRecords,
    QueryResult,
    ConnectionInfo,
    CreateTableRequest,
    ColumnDefinition,
)


class BaseDataSource(ABC):
    """Base contract for any data adapter (SQLite, CSV, JSON, XML)."""

    @abstractmethod
    def connect(self, path: str) -> ConnectionInfo:
        """Establish a connection with the data resource."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the active connection."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Indicate whether there is an open and valid connection."""
        pass

    @abstractmethod
    def get_connection_info(self) -> ConnectionInfo:
        """Return the metadata of the current connection."""
        pass

    @abstractmethod
    def list_collections(self) -> List[TableSummary]:
        """List the available collections (tables/views/sheets/files)."""
        pass

    @abstractmethod
    def get_schema(self, collection_name: str) -> TableSchema:
        """Get the descriptive schema of a collection."""
        pass

    @abstractmethod
    def get_records(self, collection_name: str, pagination: PaginationParams) -> PaginatedRecords:
        """Get paginated, filtered, and sorted records."""
        pass

    @abstractmethod
    def insert_record(self, collection_name: str, values: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new record into the collection."""
        pass

    @abstractmethod
    def update_record(
        self, collection_name: str, pk_values: Dict[str, Any], values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a record identified by its primary keys."""
        pass

    @abstractmethod
    def delete_record(self, collection_name: str, pk_values: Dict[str, Any]) -> bool:
        """Delete a record identified by its primary keys."""
        pass

    @abstractmethod
    def create_table(self, request: CreateTableRequest) -> bool:
        """Create a new table or collection."""
        pass

    @abstractmethod
    def add_column(self, collection_name: str, column: ColumnDefinition) -> bool:
        """Add a column to an existing table."""
        pass

    @abstractmethod
    def rename_table(self, collection_name: str, new_name: str) -> bool:
        """Rename an existing table."""
        pass

    @abstractmethod
    def drop_table(self, collection_name: str) -> bool:
        """Delete a collection or table."""
        pass

    @abstractmethod
    def execute_query(self, query: str) -> QueryResult:
        """Run a native direct query (SQL in SQLite)."""
        pass

    @abstractmethod
    def get_query_records(self, query: str, pagination: PaginationParams) -> PaginatedRecords:
        """Get paginated, filtered, and sorted records from an arbitrary query/view."""
        pass
