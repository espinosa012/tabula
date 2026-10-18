"""Router for database connections and local filesystem browsing."""
import os
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.adapters.sqlite import SQLiteDataSource
from backend.app.core.manager import db_manager
from backend.app.core.models import ConnectionInfo, FsBrowseResponse, FsItem

router = APIRouter(prefix="/api", tags=["Connection & Filesystem"])


class OpenDatabaseRequest(BaseModel):
    path: str


class CreateDatabaseRequest(BaseModel):
    path: str


@router.post("/connection/open", response_model=ConnectionInfo)
def open_database(req: OpenDatabaseRequest):
    """Open an existing SQLite database file."""
    if not req.path.strip():
        raise HTTPException(status_code=400, detail="The file path cannot be empty.")

    ds = SQLiteDataSource()
    try:
        info = ds.connect(req.path)
        db_manager.set_active_source(ds)
        return info
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error opening the database: {str(e)}")


@router.post("/connection/create", response_model=ConnectionInfo)
def create_database(req: CreateDatabaseRequest):
    """Create a new clean SQLite database and connect to it."""
    clean_path = req.path.strip()
    if not clean_path:
        raise HTTPException(status_code=400, detail="The file path cannot be empty.")

    ds = SQLiteDataSource()
    try:
        info = ds.create_database(clean_path)
        db_manager.set_active_source(ds)
        return info
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating the database: {str(e)}")


@router.get("/connection/status", response_model=ConnectionInfo)
def get_connection_status():
    """Get the status of the active connection."""
    return db_manager.get_connection_info()


@router.post("/connection/close")
def close_connection():
    """Close the active connection."""
    db_manager.disconnect()
    return {"status": "disconnected"}


@router.get("/connection/recent", response_model=List[str])
def get_recent_connections():
    """Get the list of recently connected paths."""
    return db_manager.get_recent_paths()


@router.get("/fs/browse", response_model=FsBrowseResponse)
def browse_filesystem(path: Optional[str] = Query(None)):
    """Browse folders and files on the local system to ease selection."""
    try:
        target_dir = Path(path).expanduser().resolve() if path else Path.cwd()
        if not target_dir.exists() or not target_dir.is_dir():
            target_dir = Path.cwd()

        parent_path = str(target_dir.parent) if target_dir.parent != target_dir else None

        items: List[FsItem] = []
        try:
            entries = sorted(os.scandir(target_dir), key=lambda e: (not e.is_dir(), e.name.lower()))
            for entry in entries:
                # Skip hidden files/folders that start with a dot
                if entry.name.startswith("."):
                    continue

                is_dir = entry.is_dir()
                size = None
                is_db = False

                if not is_dir:
                    ext = Path(entry.name).suffix.lower()
                    if ext in (".db", ".sqlite", ".sqlite3"):
                        is_db = True
                    try:
                        size = entry.stat().st_size
                    except Exception:
                        size = None

                items.append(
                    FsItem(
                        name=entry.name,
                        path=entry.path,
                        is_dir=is_dir,
                        size_bytes=size,
                        is_db=is_db,
                    )
                )
        except PermissionError:
            raise HTTPException(status_code=403, detail="Permission denied to read this directory.")

        return FsBrowseResponse(
            current_path=str(target_dir),
            parent_path=parent_path,
            items=items,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error browsing directory: {str(e)}")
