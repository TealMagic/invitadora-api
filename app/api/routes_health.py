from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import get_settings
from app.db.session import check_db_connection, get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    settings = get_settings()
    db_ok = check_db_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "environment": settings.app_env,
        "database": "connected" if db_ok else "disconnected",
    }


@router.get("/ready")
def ready():
    db_ok = check_db_connection()
    if not db_ok:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Database not ready")
    return {"status": "ready"}
