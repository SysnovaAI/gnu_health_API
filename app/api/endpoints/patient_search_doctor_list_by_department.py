from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from typing import List
from ..models.base import get_db

router = APIRouter(
    prefix="/doctor-search",
    tags=["Doctor Search"]
)

@router.get("/by-department/{department}")
def search_doctors_by_department(
    department: str,
    db: Session = Depends(get_db)
):
    """
    Search doctors by department following these steps:
    1. Find specialty id from gnuhealth_specialty using department name
    2. Use that specialty id to find hp_specialty id from gnuhealth_hp_specialty
    3. Use hp_specialty id to find doctors from gnuhealth_healthprofessional where main_specialty matches
    """
    try:
        # Step 1: Get specialty ID from gnuhealth_specialty table
        specialty_query = text("""
            SELECT id 
            FROM gnuhealth_specialty 
            WHERE name = :department
        """)
        
        specialty_result = db.execute(specialty_query, {"department": department}).fetchone()
        
        if not specialty_result:
            return {
                "error": True,
                "message": f"Specialty '{department}' not found in gnuhealth_specialty table",
                "doctors": []
            }
            
        specialty_id = specialty_result[0]
   
        # Step 3: Get doctors from gnuhealth_healthprofessional where main_specialty matches
        doctors_query = text("""
            SELECT ghp.id as healthprof_id, pp.name as doctor_name, pp.gender, pp.mobile_number,pp.photo,go2.name as degree,gs.name as doctor_speciality,ghp.year_of_experience,ru.email
                FROM gnuhealth_healthprofessional ghp
                join party_party pp on (ghp.name = pp.id)
                JOIN res_user ru ON (pp.internal_user = ru.id)
                join gnuhealth_hp_specialty ghs on (ghp.main_specialty = ghs.id)
                join gnuhealth_specialty gs on (ghs.specialty = gs.id)
                join gnuhealth_occupation go2 on (pp.occupation = go2.id)
                WHERE gs.id = :hp_specialty_id
        """)
            
        doctors = db.execute(doctors_query, {"hp_specialty_id": specialty_id}).fetchall()
     
        if not doctors:
            return {
                "error": True,
                "message": f"No doctors found with main_specialty = {specialty_id}",
                "doctors": []
            }
        

        specialities_info = [
            {
            "healthprof_id": row.healthprof_id, 
            "doctor_name": row.doctor_name,
            "gender": row.gender,
            "mobile_number": row.mobile_number,
            "photo": row.photo,
            "degree": row.degree,
            "speciality_name": row.doctor_speciality,
            "year_of_experience": row.year_of_experience,
            "email": row.email
            } for row in doctors
            ]
        
        return {
            "Status": True,
            "specialty_id": specialty_id,
            "message": specialities_info
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error searching doctors: {str(e)}"
        )

@router.get("/list-specialties")
def list_specialties(db: Session = Depends(get_db)):
    """List all available specialties with their IDs"""
    try:
        query = text("""
            SELECT id, name 
            FROM gnuhealth_specialty 
            ORDER BY name
        """)
        results = db.execute(query).fetchall()
        return [{
            "id": row[0],
            "name": row[1]
        } for row in results]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listing specialties: {str(e)}"
        )

@router.get("/list-departments")
def list_departments(db: Session = Depends(get_db)):
    """
    Get a list of all available departments/specialties.
    Useful for showing available options to users.
    """
    try:
        query = text("""
            SELECT DISTINCT name 
            FROM gnuhealth_specialty 
            ORDER BY name
        """)
        
        results = db.execute(query).fetchall()
        
        if not results:
            return {"departments": []}
            
        departments = [row[0] for row in results]
        
        return {
            "departments": departments
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching departments: {str(e)}"
        )
