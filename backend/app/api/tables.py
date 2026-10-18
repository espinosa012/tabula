"""Router for DDL operations and table inspection."""
from typing import List
from fastapi import APIRouter, HTTPException

from backend.app.core.manager import db_manager
from backend.app.core.models import (
    TableSummary,
    TableSchema,
    CreateTableRequest,
    AddColumnRequest,
    RenameTableRequest,
)

router = APIRouter(prefix="/api/tables", tags=["Tables & Schema"])


def _get_active_source():
    """Helper to verify an active connection."""
    if not db_manager.is_connected():
        raise HTTPException(status_code=400, detail="No database is connected.")
    return db_manager.get_active_source()


@router.get("", response_model=List[TableSummary])
def list_tables():
    """List all available tables and views."""
    source = _get_active_source()
    try:
        return source.list_collections()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/schema", response_model=TableSchema)
def get_table_schema(name: str):
    """Get the column and constraint schema of a table."""
    source = _get_active_source()
    try:
        return source.get_schema(name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
def create_table(req: CreateTableRequest):
    """Create a new table."""
    source = _get_active_source()
    try:
        source.create_table(req)
        return {"status": "created", "table": req.name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating table: {str(e)}")


@router.post("/{name}/alter")
def add_column_to_table(name: str, req: AddColumnRequest):
    """Add a column to an existing table."""
    source = _get_active_source()
    try:
        source.add_column(name, req.column)
        return {"status": "altered", "table": name, "column": req.column.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding column: {str(e)}")


@router.post("/{name}/rename")
def rename_table(name: str, req: RenameTableRequest):
    """Rename an existing table (ALTER TABLE RENAME TO)."""
    source = _get_active_source()
    try:
        source.rename_table(name, req.new_name)
        return {"status": "renamed", "table": name, "new_name": req.new_name.strip()}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error renaming table: {str(e)}")


@router.delete("/{name}/drop")
def drop_table(name: str):
    """Delete a table or view."""
    source = _get_active_source()
    try:
        source.drop_table(name)
        return {"status": "dropped", "table": name}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error dropping table: {str(e)}")
