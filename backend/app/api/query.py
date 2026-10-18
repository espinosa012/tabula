"""Router for the SQL console and execution of arbitrary queries."""
from fastapi import APIRouter, HTTPException

from backend.app.core.manager import db_manager
from backend.app.core.models import ExecuteQueryRequest, QueryResult

router = APIRouter(prefix="/api/query", tags=["SQL Query Console"])


@router.post("", response_model=QueryResult)
def execute_query(req: ExecuteQueryRequest):
    """Run an arbitrary SQL statement on the active database."""
    if not db_manager.is_connected():
        raise HTTPException(status_code=400, detail="No database is connected.")

    source = db_manager.get_active_source()
    try:
        return source.execute_query(req.query)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error while running the query: {str(e)}")
