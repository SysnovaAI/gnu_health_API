from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from typing import List
from pydantic import BaseModel
from ..models.base import get_db

public_router = APIRouter()

# Pydantic model for Lab Test Criteria Details (as requested)
class TestNameDetail(BaseModel):
    id: int
    code: str | None
    gnuhealth_lab_id: int | None
    name: str
    test_type_id: int

# Pydantic models for response
class LabTestType(BaseModel):
    id: int
    code: str
    name: str
    info: str | None
    active: bool
    product_id: int
    testname: List[TestNameDetail]

class LabTestTypeResponse(BaseModel):
    success: bool
    message: str
    test_types: List[LabTestType]

def get_lab_test_types(db: Session) -> dict:
    """
    Helper function to get all lab test types
    """
    try:
        # Query to get all lab test types
        query = text("""
            SELECT 
                id,
                code,
                name,
                info,
                active,
                product_id
            FROM gnuhealth_lab_test_type
            ORDER BY name
        """)
        
        results = db.execute(query).fetchall()
        
        if not results:
            return {
                "success": True,
                "message": "No lab test types found",
                "test_types": []
            }
        
        # Get the IDs of the test types found
        test_type_ids = [test.id for test in results]

        # Query to get specific criteria details for these test types
        criteria_query = text("""
            SELECT 
                id, 
                code, 
                gnuhealth_lab_id, 
                name, 
                test_type_id
            FROM gnuhealth_lab_test_critearea
            WHERE test_type_id = ANY(:test_type_ids)
            ORDER BY test_type_id, sequence, name -- Added sequence for consistent ordering if available
        """)
        
        criteria_results = db.execute(criteria_query, {"test_type_ids": test_type_ids}).fetchall()
        
        # Organize criteria details by test_type_id
        criteria_map = {}
        for crit in criteria_results:
            crit_dict = {
                "id": crit.id,
                "code": crit.code,
                "gnuhealth_lab_id": crit.gnuhealth_lab_id,
                "name": crit.name,
                "test_type_id": crit.test_type_id
            }
            if crit.test_type_id not in criteria_map:
                criteria_map[crit.test_type_id] = []
            criteria_map[crit.test_type_id].append(crit_dict)

        # Format the results including criteria details under 'testname'
        test_types = [
            {
                "id": test.id,
                "code": test.code,
                "name": test.name,
                "info": test.info,
                "active": test.active,
                "product_id": test.product_id,
                "testname": criteria_map.get(test.id, []) # Add criteria list under 'testname'
            } for test in results
        ]
        
        return {
            "success": True,
            "message": f"Found {len(test_types)} lab test types",
            "test_types": test_types
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving lab test types: {str(e)}"
        )

@public_router.get("/test-categories", response_model=LabTestTypeResponse)
def get_all_lab_test_types_public(db: Session = Depends(get_db)):
    """
    Get all laboratory test types from gnuhealth_lab_test_type table.
    This is a public endpoint that doesn't require authentication.
    """
    return get_lab_test_types(db)
