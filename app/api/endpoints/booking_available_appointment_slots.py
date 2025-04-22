from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from datetime import datetime, timedelta, date
from typing import Optional, List
from pydantic import BaseModel
from app.api.deps import get_db

router = APIRouter()
public_router = APIRouter()

class DoctorInfo(BaseModel):
    id: int
    name: str
    specialty: str

class AvailableSlot(BaseModel):
    id: int
    appointment_date: str
    doctor_id: int
    doctor_name: str
    specialty: str
    institution_id: int
    institution_name: str

class AvailableSlotsResponse(BaseModel):
    success: bool
    message: str
    slots: List[AvailableSlot]

class CheckSlotsRequest(BaseModel):
    appointment_date: Optional[date] = None
    appointment_type: Optional[str] = None
    state: Optional[str] = None

@router.get("/slots/{healthprof}/{date}", response_model=AvailableSlotsResponse)
def get_available_slots(
    healthprof: int,
    date: str,
    db: Session = Depends(get_db)
):
    """Get available appointment slots for a specific doctor and date"""
    
    # First check if the doctor exists
    doctor_query = text("""
        SELECT 
            ghp.id,
            pp.name AS doctor_name,
            ghp.main_specialty
        FROM gnuhealth_healthprofessional ghp
        JOIN party_party pp ON ghp.name = pp.id
        WHERE ghp.id = :healthprof
    """)
    
    doctor = db.execute(doctor_query, {"healthprof": healthprof}).first()
    
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    
    # Build the query for available slots
    slots_query = text("""
        SELECT 
            ga.id,
            ga.appointment_date,
            ghp.id AS doctor_id,
            pp.name AS doctor_name,
            ghp.main_specialty,
            ga.institution AS institution_id,
            gi.name AS institution_name
        FROM gnuhealth_appointment ga
        JOIN gnuhealth_healthprofessional ghp ON ga.healthprof = ghp.id
        JOIN party_party pp ON ghp.name = pp.id
        JOIN gnuhealth_institution gi ON ga.institution = gi.id
        WHERE ga.state = 'free'
        AND ga.healthprof = :healthprof
        AND DATE(ga.appointment_date) = :date
        ORDER BY ga.appointment_date ASC
    """)
    
    results = db.execute(slots_query, {
        "healthprof": healthprof,
        "date": date
    }).fetchall()
    
    # Format the results
    available_slots = [
        {
            "id": slot.id,
            "appointment_date": slot.appointment_date.strftime("%Y-%m-%d %H:%M:%S.000") if isinstance(slot.appointment_date, datetime) else slot.appointment_date,
            "doctor_id": slot.doctor_id,
            "doctor_name": slot.doctor_name,
            "specialty": slot.specialty,
            "institution_id": slot.institution_id,
            "institution_name": slot.institution_name
        } for slot in results
    ]
    
    return {
        "success": True,
        "message": f"Available slots found for Dr. {doctor.doctor_name} on {date}",
        "slots": available_slots
    }

@router.get("/doctors")
def get_doctors(db: Session = Depends(get_db)):
    """Get list of all doctors"""
    
    query = text("""
        SELECT 
            ghp.id,
            pp.name,
            ghp.main_specialty
        FROM gnuhealth_healthprofessional ghp
        JOIN party_party pp ON ghp.name = pp.id
        ORDER BY pp.name
    """)
    
    results = db.execute(query).fetchall()
    
    if not results:
        return {"success": True, "doctors": []}
        
    doctors = [
        {
            "id": doc.id,
            "name": doc.name,
            "specialty": doc.specialty
        } for doc in results
    ]
    
    return {"success": True, "doctors": doctors}

@public_router.get("/slots", response_model=AvailableSlotsResponse)
def get_available_slots_public(
    healthprof: int,
    date: str,
    db: Session = Depends(get_db)
):
    """Get available appointment slots for a specific doctor and date (public access)"""
    
    # First check if the doctor exists
    doctor_query = text("""
        SELECT 
            ghp.id,
            pp.name AS doctor_name,
            ghp.main_specialty
        FROM gnuhealth_healthprofessional ghp
        JOIN party_party pp ON ghp.name = pp.id
        WHERE ghp.id = :healthprof
    """)
    
    doctor = db.execute(doctor_query, {"healthprof": healthprof}).first()
    
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    
    # Build the query for available slots
    slots_query = text("""
        SELECT 
            ga.id,
            ga.appointment_date,
            ghp.id AS doctor_id,
            pp.name AS doctor_name,
            ghp.main_specialty,
            ga.institution AS institution_id,
            gi.name AS institution_name
        FROM gnuhealth_appointment ga
        JOIN gnuhealth_healthprofessional ghp ON ga.healthprof = ghp.id
        JOIN party_party pp ON ghp.name = pp.id
        JOIN gnuhealth_institution gi ON ga.institution = gi.id
        WHERE ga.state = 'free'
        AND ga.healthprof = :healthprof
        AND DATE(ga.appointment_date) = :date
        ORDER BY ga.appointment_date ASC
    """)
    
    results = db.execute(slots_query, {
        "healthprof": healthprof,
        "date": date
    }).fetchall()
    
    # Format the results
    available_slots = [
        {
            "id": slot.id,
            "appointment_date": slot.appointment_date.strftime("%Y-%m-%d %H:%M:%S.000") if isinstance(slot.appointment_date, datetime) else slot.appointment_date,
            "doctor_id": slot.doctor_id,
            "doctor_name": slot.doctor_name,
            "specialty": slot.specialty,
            "institution_id": slot.institution_id,
            "institution_name": slot.institution_name
        } for slot in results
    ]
    
    return {
        "success": True,
        "message": f"Available slots found for Dr. {doctor.doctor_name} on {date}",
        "slots": available_slots
    }

@public_router.get("/doctors")
def get_doctors_public(db: Session = Depends(get_db)):
    """Get list of all doctors (public access)"""
    
    query = text("""
        SELECT 
            ghp.id,
            pp.name,
            ghp.main_specialty
        FROM gnuhealth_healthprofessional ghp
        JOIN party_party pp ON ghp.name = pp.id
        ORDER BY pp.name
    """)
    
    results = db.execute(query).fetchall()
    
    if not results:
        return {"success": True, "doctors": []}
        
    doctors = [
        {
            "id": doc.id,
            "name": doc.name,
            "specialty": doc.specialty
        } for doc in results
    ]
    
    return {"success": True, "doctors": doctors}

@public_router.post("/check-available-slots", operation_id="check_available_slots")
async def check_slots(request: CheckSlotsRequest, db=Depends(get_db)):
    """
    Check available appointment slots with optional filters.
    """
    try:
        # Get health_prof_id from session (you'll need to implement this)
        health_prof_id = 1  # Replace with actual session logic
        
        # Base query
        query = """
            SELECT 
                a.id,
                a.health_prof_id,
                a.appointment_date,
                a.start_time,
                a.end_time,
                a.appointment_type,
                a.state,
                a.is_booked,
                a.created_at,
                a.updated_at
            FROM gnuhealth_appointment_slots a
            WHERE a.health_prof_id = :health_prof_id
        """
        
        params = {"health_prof_id": health_prof_id}
        
        # Add filters based on provided parameters
        if request.appointment_date:
            query += " AND a.appointment_date = :appointment_date"
            params["appointment_date"] = request.appointment_date
            
        if request.appointment_type:
            query += " AND a.appointment_type = :appointment_type"
            params["appointment_type"] = request.appointment_type
            
        if request.state:
            query += " AND a.state = :state"
            params["state"] = request.state
            
        # Execute query
        result = db.execute(text(query), params)
        slots = [dict(row) for row in result]
        
        return {
            "status": "success",
            "message": "Available slots retrieved successfully",
            "data": slots
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking available slots: {str(e)}"
        )

# Add other endpoints to the appropriate router
# router.include_router(...) for authenticated endpoints
# public_router.include_router(...) for public endpoints
