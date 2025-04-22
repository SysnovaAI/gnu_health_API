from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from typing import List
from pydantic import BaseModel
from ..models.base import get_db

router = APIRouter()
public_router = APIRouter()

class Specialty(BaseModel):
    id: int
    code: str
    name: str

class SpecialtyResponse(BaseModel):
    success: bool
    message: str
    specialties: List[Specialty]

@router.get("/specialties", response_model=SpecialtyResponse)
def get_all_specialties(db: Session = Depends(get_db)):
    """
    Get all specialties with their id, code, and name from the gnuhealth_specialty table.
    """
    try:
        # Query to get all specialties
        query = text("""
            SELECT 
                id,
                code,
                name
            FROM gnuhealth_specialty
            ORDER BY name
        """)
        
        results = db.execute(query).fetchall()
        
        if not results:
            return {
                "success": True,
                "message": "No specialties found",
                "specialties": []
            }
        
        # Format the results
        specialties = [
            {
                "id": specialty.id,
                "code": specialty.code,
                "name": specialty.name
            } for specialty in results
        ]
        
        return {
            "success": True,
            "message": f"Found {len(specialties)} specialties",
            "specialties": specialties
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving specialties: {str(e)}"
        )

# Public endpoint (no authentication required)
@public_router.get("/specialties", response_model=SpecialtyResponse)
def get_all_specialties_public(db: Session = Depends(get_db)):
    """
    Get all specialties with their id, code, and name from the gnuhealth_specialty table.
    This is a public endpoint that doesn't require authentication.
    """
    try:
        # Query to get all specialties
        query = text("""
            SELECT 
                id,
                code,
                name
            FROM gnuhealth_specialty
            ORDER BY name
        """)
        
        results = db.execute(query).fetchall()
        
        if not results:
            return {
                "success": True,
                "message": "No specialties found",
                "specialties": []
            }
        
        # Format the results
        specialties = [
            {
                "id": specialty.id,
                "code": specialty.code,
                "name": specialty.name
            } for specialty in results
        ]
        
        return {
            "success": True,
            "message": f"Found {len(specialties)} specialties",
            "specialties": specialties
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving specialties: {str(e)}"
        )
