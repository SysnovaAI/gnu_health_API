from fastapi import APIRouter, Depends
from sqlalchemy import text
from app.api.database import get_db
from sqlalchemy.orm import Session
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
        # Check database connection
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        db_status = "unhealthy"

    return {
        "status": "healthy",
        "database": db_status,
        "version": "1.0.0"
    } 