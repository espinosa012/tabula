"""API router for managing and querying user-defined custom views."""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.app.core.manager import db_manager
from backend.app.core.models import (
    CustomView,
    CustomViewCreate,
    CustomViewUpdate,
    PaginatedRecords,
    PaginationParams,
)
from backend.app.core.views_store import views_store

router = APIRouter(prefix="/api/views", tags=["Custom Views"])


@router.get("", response_model=List[CustomView])
def list_views(all_views: bool = Query(False, alias="all")):
    """List custom views saved in local JSON.
    
    If 'all' is False and a database is currently connected, returns views
    matching the connected database path (or global views).
    """
    db_path = None
    if not all_views and db_manager.is_connected():
        db_path = db_manager.get_active_source().get_connection_info().path

    return views_store.list_views(db_path=db_path, all_views=all_views)


@router.post("", response_model=CustomView, status_code=status.HTTP_201_CREATED)
def create_view(req: CustomViewCreate):
    """Create and save a new custom view in local JSON."""
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="View name cannot be empty.")

    sql = req.sql.strip()
    if not sql:
        raise HTTPException(status_code=400, detail="View SQL query cannot be empty.")

    db_path = req.db_path
    if not db_path and db_manager.is_connected():
        db_path = db_manager.get_active_source().get_connection_info().path

    # If database is connected, validate that the query can be executed
    if db_manager.is_connected():
        source = db_manager.get_active_source()
        try:
            source.get_query_records(sql, PaginationParams(page=1, page_size=1))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid SQL query for view: {str(e)}")

    return views_store.create_view(
        name=name,
        sql=sql,
        description=req.description,
        db_path=db_path,
    )


@router.post("/preview", response_model=PaginatedRecords)
def preview_view(req: CustomViewCreate):
    """Preview records of a SQL query before saving."""
    if not db_manager.is_connected():
        raise HTTPException(status_code=400, detail="No database is connected.")

    sql = req.sql.strip()
    if not sql:
        raise HTTPException(status_code=400, detail="SQL query cannot be empty.")

    source = db_manager.get_active_source()
    try:
        return source.get_query_records(sql, PaginationParams(page=1, page_size=10))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query error: {str(e)}")


@router.get("/{view_id}", response_model=CustomView)
def get_view(view_id: str):
    """Get metadata of a custom view by ID."""
    view = views_store.get_view(view_id)
    if not view:
        raise HTTPException(status_code=404, detail=f"Custom view '{view_id}' not found.")
    return view


@router.put("/{view_id}", response_model=CustomView)
def update_view(view_id: str, req: CustomViewUpdate):
    """Update name, SQL query, or description of a custom view."""
    view = views_store.get_view(view_id)
    if not view:
        raise HTTPException(status_code=404, detail=f"Custom view '{view_id}' not found.")

    if req.name is not None and not req.name.strip():
        raise HTTPException(status_code=400, detail="View name cannot be empty.")

    if req.sql is not None:
        sql = req.sql.strip()
        if not sql:
            raise HTTPException(status_code=400, detail="View SQL query cannot be empty.")
        if db_manager.is_connected():
            source = db_manager.get_active_source()
            try:
                source.get_query_records(sql, PaginationParams(page=1, page_size=1))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid SQL query for view: {str(e)}")

    updated = views_store.update_view(
        view_id=view_id,
        name=req.name,
        sql=req.sql,
        description=req.description,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Custom view '{view_id}' not found.")
    return updated


@router.delete("/{view_id}")
def delete_view(view_id: str):
    """Delete a custom view from local JSON storage."""
    deleted = views_store.delete_view(view_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Custom view '{view_id}' not found.")
    return {"status": "deleted", "id": view_id}


@router.get("/{view_id}/records", response_model=PaginatedRecords)
def get_view_records(
    view_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    sort_by: Optional[str] = Query(None),
    sort_dir: str = Query("asc", pattern="^(asc|desc|ASC|DESC)$"),
    search: Optional[str] = Query(None),
):
    """Get paginated, filtered, and sorted records from a custom view."""
    if not db_manager.is_connected():
        raise HTTPException(status_code=400, detail="No database is connected.")

    view = views_store.get_view(view_id)
    if not view:
        raise HTTPException(status_code=404, detail=f"Custom view '{view_id}' not found.")

    pagination = PaginationParams(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
    )

    source = db_manager.get_active_source()
    try:
        return source.get_query_records(view.sql, pagination)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error executing custom view query: {str(e)}")
