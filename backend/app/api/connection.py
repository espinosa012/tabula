"""Router for database connections and local filesystem browsing."""
import os
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.adapters.mongo import MongoDataSource
from backend.app.adapters.postgres import PostgreSQLDataSource
from backend.app.adapters.sqlite import SQLiteDataSource
from backend.app.core.config import get_config
from backend.app.core.manager import db_manager
from backend.app.core.models import (
    AppConfig,
    ConnectionInfo,
    FsBrowseResponse,
    FsItem,
    MongoConnectRequest,
    MongoTestResponse,
    PostgresConnectRequest,
    PostgresTestResponse,
)

router = APIRouter(prefix="/api", tags=["Connection & Filesystem"])


class OpenDatabaseRequest(BaseModel):
    path: str


class CreateDatabaseRequest(BaseModel):
    path: str


@router.post("/connection/open", response_model=ConnectionInfo)
def open_database(req: OpenDatabaseRequest):
    """Open an existing SQLite database file."""
    clean_path = req.path.strip().strip("'\"")
    if not clean_path:
        raise HTTPException(status_code=400, detail="The file path cannot be empty.")

    ds = SQLiteDataSource()
    try:
        info = ds.connect(clean_path)
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
    clean_path = req.path.strip().strip("'\"")
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


@router.post("/connection/postgres/test", response_model=PostgresTestResponse)
def test_postgres_connection(req: PostgresConnectRequest):
    """Test PostgreSQL connection without activating session."""
    try:
        if req.mode == "uri" and req.uri:
            res = PostgreSQLDataSource.test_connection(uri=req.uri)
        elif req.params:
            res = PostgreSQLDataSource.test_connection(
                host=req.params.host,
                port=req.params.port,
                database=req.params.database,
                user=req.params.user,
                password=req.params.password,
                sslmode=req.params.sslmode,
            )
        else:
            raise HTTPException(status_code=400, detail="Missing connection parameters or URI.")
        return PostgresTestResponse(**res)
    except Exception as e:
        return PostgresTestResponse(
            success=False,
            message=f"Connection failed: {str(e)}",
        )


@router.post("/connection/postgres/connect", response_model=ConnectionInfo)
def connect_postgres(req: PostgresConnectRequest):
    """Connect to a PostgreSQL database and set as active source."""
    ds = PostgreSQLDataSource()
    try:
        if req.mode == "uri" and req.uri:
            info = ds.connect(path=req.uri)
        elif req.params:
            info = ds.connect(
                host=req.params.host,
                port=req.params.port,
                database=req.params.database,
                user=req.params.user,
                password=req.params.password,
                sslmode=req.params.sslmode,
            )
        else:
            raise HTTPException(status_code=400, detail="Missing connection parameters or URI.")
        db_manager.set_active_source(ds)
        return info
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to connect to PostgreSQL: {str(e)}")


@router.post("/connection/mongo/test", response_model=MongoTestResponse)
def test_mongo_connection(req: MongoConnectRequest):
    """Test MongoDB connection without activating the session."""
    try:
        if req.mode == "uri" and req.uri:
            res = MongoDataSource.test_connection(uri=req.uri)
        elif req.params:
            res = MongoDataSource.test_connection(
                host=req.params.host,
                port=req.params.port,
                database=req.params.database,
                user=req.params.user,
                password=req.params.password,
                auth_source=req.params.auth_source,
                tls=req.params.tls,
            )
        else:
            raise HTTPException(status_code=400, detail="Missing connection parameters or URI.")
        return MongoTestResponse(**res)
    except HTTPException:
        raise
    except Exception as e:
        return MongoTestResponse(
            success=False,
            message=f"Connection failed: {str(e)}",
        )


@router.post("/connection/mongo/connect", response_model=ConnectionInfo)
def connect_mongo(req: MongoConnectRequest):
    """Connect to a MongoDB database and set it as the active source."""
    ds = MongoDataSource()
    try:
        if req.mode == "uri" and req.uri:
            info = ds.connect(path=req.uri)
        elif req.params:
            info = ds.connect(
                host=req.params.host,
                port=req.params.port,
                database=req.params.database,
                user=req.params.user,
                password=req.params.password,
                auth_source=req.params.auth_source,
                tls=req.params.tls,
            )
        else:
            raise HTTPException(status_code=400, detail="Missing connection parameters or URI.")
        db_manager.set_active_source(ds)
        return info
    except HTTPException:
        ds.close()
        raise
    except Exception as e:
        ds.close()
        raise HTTPException(status_code=400, detail=f"Failed to connect to MongoDB: {str(e)}")


@router.get("/connection/status", response_model=ConnectionInfo)
def get_connection_status():
    """Get the status of the active connection."""
    return db_manager.get_connection_info()


@router.post("/connection/close")
def close_connection():
    """Close the active connection."""
    db_manager.disconnect()
    return {"status": "disconnected"}


@router.get("/config", response_model=AppConfig)
def get_app_config():
    """Get user-configurable application settings."""
    return AppConfig(**get_config())


@router.get("/connection/recent", response_model=List[str])
def get_recent_connections():
    """Get the list of recently connected paths."""
    return db_manager.get_recent_paths()


@router.get("/fs/browse", response_model=FsBrowseResponse)
def browse_filesystem(path: Optional[str] = Query(None)):
    """Browse folders and files on the local system to ease selection."""
    try:
        target_path = Path(path).expanduser().resolve() if path else Path.cwd()
        if target_path.is_file():
            target_dir = target_path.parent
        elif target_path.is_dir():
            target_dir = target_path
        elif target_path.parent.is_dir():
            target_dir = target_path.parent
        else:
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
