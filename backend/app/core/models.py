"""Pydantic models for the vg-data-visor core."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ColumnDefinition(BaseModel):
    """Definition of a table column."""
    name: str
    type: str = "TEXT"
    is_pk: bool = False
    not_null: bool = False
    default_value: Optional[str] = None
    auto_increment: bool = False


class TableSchema(BaseModel):
    """Structural schema of a table or view."""
    name: str
    type: str = "table"  # 'table' or 'view'
    columns: List[ColumnDefinition]
    pk_columns: List[str] = Field(default_factory=list)
    sql: Optional[str] = None


class TableSummary(BaseModel):
    """Summary of a collection (table or view)."""
    name: str
    type: str = "table"
    row_count: Optional[int] = None


class PaginationParams(BaseModel):
    """Parameters for paginating and sorting records."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)
    sort_by: Optional[str] = None
    sort_dir: str = Field(default="asc", pattern="^(asc|desc|ASC|DESC)$")
    search: Optional[str] = None


class PaginatedRecords(BaseModel):
    """Paginated result of records."""
    total: int
    page: int
    page_size: int
    total_pages: int
    columns: List[str]
    records: List[Dict[str, Any]]
    pk_columns: List[str] = Field(default_factory=list)


class QueryResult(BaseModel):
    """Result of running an arbitrary SQL query."""
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0
    message: Optional[str] = None


class ConnectionInfo(BaseModel):
    """Information about the active connection."""
    path: str
    connected: bool
    size_bytes: int = 0
    tables_count: int = 0


class CreateTableRequest(BaseModel):
    """Request to create a new table."""
    name: str
    columns: List[ColumnDefinition]


class AddColumnRequest(BaseModel):
    """Request to add a column to a table."""
    column: ColumnDefinition


class ExecuteQueryRequest(BaseModel):
    """Request to execute free-form SQL."""
    query: str


class RecordCreateRequest(BaseModel):
    """Request to insert a record."""
    values: Dict[str, Any]


class RecordUpdateRequest(BaseModel):
    """Request to update an existing record."""
    pk_values: Dict[str, Any]
    values: Dict[str, Any]


class RecordDeleteRequest(BaseModel):
    """Request to delete a record."""
    pk_values: Dict[str, Any]


class FsItem(BaseModel):
    """Item in the filesystem browser."""
    name: str
    path: str
    is_dir: bool
    size_bytes: Optional[int] = None
    is_db: bool = False


class FsBrowseResponse(BaseModel):
    """Response from the server folder browser."""
    current_path: str
    parent_path: Optional[str]
    items: List[FsItem]
