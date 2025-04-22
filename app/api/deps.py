from sqlalchemy.orm import Session
from app.api.models.base import get_db

def get_db():
    """
    Database dependency function that yields a database session.
    """
    db = get_db()
    try:
        yield db
    finally:
        db.close() 