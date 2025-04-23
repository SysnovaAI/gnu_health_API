from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.models.base import get_db
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint to verify the application and database status.
    Returns:
        dict: Status of the application and database
    """
    try:
        # Test database connection
        db.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)} 