from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from typing import List
from pydantic import BaseModel
from ..models.base import get_db

public_router = APIRouter()

# Pydantic model for Medicine Details
class MedicineDetail(BaseModel):
    id: int
    name: int | None  # This is the party_party ID
    active_component: str
    code: str | None
    active: bool

# Pydantic model for response
class MedicineListResponse(BaseModel):
    success: bool
    message: str
    medicines: List[MedicineDetail]

def get_medicines(db: Session) -> dict:
    """
    Helper function to get all medicines
    """
    try:
        # Query to get all medicines with their party details
        query = text("""
            SELECT 
                gm.id,
                gm.name as party_id,
                gm.active_component,
                pp.code,
                gm.active
            FROM gnuhealth_medicament gm
            LEFT JOIN party_party pp ON gm.name = pp.id
            ORDER BY gm.active_component
        """)
        
        results = db.execute(query).fetchall()
        
        if not results:
            return {
                "success": True,
                "message": "No medicines found",
                "medicines": []
            }
        
        # Format the results
        medicines = [
            {
                "id": med.id,
                "name": med.party_id,
                "active_component": med.active_component,
                "code": med.code,
                "active": med.active
            } for med in results
        ]
        
        return {
            "success": True,
            "message": f"Found {len(medicines)} medicines",
            "medicines": medicines
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving medicines: {str(e)}"
        )

@public_router.get("/medicines", response_model=MedicineListResponse)
def get_all_medicines_public(db: Session = Depends(get_db)):
    """
    Get all medicines from gnuhealth_medicament table.
    This is a public endpoint that doesn't require authentication.
    """
    return get_medicines(db) 