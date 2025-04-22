from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi.responses import JSONResponse
from ..models.base import get_db
from .appointments import get_current_user
from pydantic import BaseModel

router = APIRouter()

class AppointmentDetailsRequest(BaseModel):
    appointment_id: int

@router.post("/prescription-header")
def get_appointment_details(
    request: AppointmentDetailsRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    try:
        # First get the patient ID from the appointment
        appointment_query = text("""
            SELECT 
                ga.id,
                ga.patient,
                ga.healthprof
            FROM gnuhealth_appointment ga
            WHERE ga.id = :appointment_id
        """)
        
        appointment = db.execute(appointment_query, {"appointment_id": request.appointment_id}).fetchone()
        
        if not appointment:
            return JSONResponse(
                content={"message": "Appointment not found"},
                status_code=404
            )
            
        # Get patient details by following the navigation path
        patient_query = text("""
            SELECT 
                pp.name as patient_name,
                pp.gender,
                pp.mobile_number,
                pp.internal_user
            FROM gnuhealth_patient gp
            JOIN party_party pp ON gp.name = pp.id
            WHERE gp.id = :patient_id
        """)
        
        patient = db.execute(patient_query, {"patient_id": appointment.patient}).fetchone()
        
        if not patient:
            return JSONResponse(
                content={"message": "Patient details not found"},
                status_code=404
            )
            
        # Get patient email from res_user using internal_user
        patient_user_query = text("""
            SELECT email
            FROM res_user
            WHERE id = :internal_user
        """)
        
        patient_user = db.execute(patient_user_query, {"internal_user": patient.internal_user}).fetchone()
        
        # Get doctor details
        doctor_query = text("""
            SELECT 
                pp.name as doctor_name,
                ghp.main_specialty,
                pp.mobile_number,
                ru.email
            FROM gnuhealth_healthprofessional ghp
            JOIN party_party pp ON ghp.name = pp.id
            JOIN res_user ru ON pp.internal_user = ru.id
            WHERE ghp.id = :healthprof_id
        """)
        
        doctor = db.execute(doctor_query, {"healthprof_id": appointment.healthprof}).fetchone()
        
        if not doctor:
            return JSONResponse(
                content={"message": "Doctor details not found"},
                status_code=404
            )
            
        # Format the response
        response = {
            "appointment_id": appointment.id,
            "patient_details": {
                "name": patient.patient_name,
                "gender": patient.gender,
                "mobile_number": patient.mobile_number,
                "email": patient_user.email if patient_user else None
            },
            "doctor_details": {
                "name": doctor.doctor_name,
                "specialization": doctor.main_specialty,
                "mobile_number": doctor.mobile_number,
                "email": doctor.email
            }
        }
        
        return JSONResponse(
            content=response,
            status_code=200
        )
        
    except Exception as e:
        return JSONResponse(
            content={"message": f"Error occurred: {str(e)}"},
            status_code=500
        ) 