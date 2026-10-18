"""Router for DML operations (records) on tables."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from backend.app.core.manager import db_manager
from backend.app.core.models import (
    PaginationParams,
    PaginatedRecords,
    RecordCreateRequest,
    RecordUpdateRequest,
    RecordDeleteRequest,
)

router = APIRouter(prefix="/api/tables", tags=["Records & DML"])


def _get_active_source():
    """Helper to verify an active connection."""
    if not db_manager.is_connected():
        raise HTTPException(status_code=400, detail="No database is connected.")
    return db_manager.get_active_source()


@router.get("/{name}/records", response_model=PaginatedRecords)
def get_records(
    name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    sort_by: Optional[str] = Query(None),
    sort_dir: str = Query("asc", pattern="^(asc|desc|ASC|DESC)$"),
    search: Optional[str] = Query(None),
):
    """Get paginated, filtered, and sorted records."""
    source = _get_active_source()
    params = PaginationParams(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
    )
    try:
        return source.get_records(name, params)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/records")
def create_record(name: str, req: RecordCreateRequest):
    """Insert a new record into the table."""
    source = _get_active_source()
    try:
        return source.insert_record(name, req.values)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error inserting record: {str(e)}")


@router.put("/{name}/records")
def update_record(name: str, req: RecordUpdateRequest):
    """Update a record identified by primary keys or _rowid_."""
    source = _get_active_source()
    try:
        return source.update_record(name, req.pk_values, req.values)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating record: {str(e)}")


@router.delete("/{name}/records")
@router.post("/{name}/records/delete")
def delete_record(name: str, req: RecordDeleteRequest):
    """Delete a record identified by primary keys or _rowid_."""
    source = _get_active_source()
    try:
        success = source.delete_record(name, req.pk_values)
        if not success:
            raise HTTPException(status_code=404, detail="No record was found to delete.")
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error deleting record: {str(e)}")
