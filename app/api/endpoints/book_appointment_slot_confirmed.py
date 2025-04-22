from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from datetime import datetime
from pydantic import BaseModel
from ..models.base import get_db
from .appointments import get_current_user

router = APIRouter()

class AppointmentBooking(BaseModel):
    appointment_id: int

@router.post("/book-slot")
def book_appointment_slot(
    booking: AppointmentBooking,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Book an available appointment slot"""
    user_id = user["id"]  # Get user ID from JWT

    # 1. First verify the user is a patient
    # Fetch party_party.id using res_user.id
    party_query = text("SELECT id FROM party_party WHERE internal_user = :user_id")
    party = db.execute(party_query, {"user_id": user_id}).fetchone()
    
    if not party:
        raise HTTPException(status_code=400, detail="User is not linked to a party entity")

    party_id = party[0]

    # Fetch gnuhealth_patient.id using party_party.id
    patient_query = text("SELECT id FROM gnuhealth_patient WHERE name = :party_id")
    patient = db.execute(patient_query, {"party_id": party_id}).fetchone()
    
    if not patient:
        raise HTTPException(status_code=400, detail="User is not registered as a patient")

    patient_id = patient[0]  # Extract patient ID

    # 2. Check if the appointment slot is available
    slot_query = text("""
        SELECT id, appointment_date, healthprof
        FROM gnuhealth_appointment
        WHERE id = :appointment_id AND state = 'free'
    """)
    
    slot = db.execute(slot_query, {"appointment_id": booking.appointment_id}).fetchone()
    
    if not slot:
        raise HTTPException(
            status_code=404, 
            detail="Appointment slot not found or already booked"
        )
    
    # 3. Check if appointment date is in the future
    appointment_date = slot[1]
    if isinstance(appointment_date, str):
        appointment_date = datetime.strptime(appointment_date, "%Y-%m-%d %H:%M:%S")
    
    if appointment_date < datetime.now():
        raise HTTPException(
            status_code=400,
            detail="Cannot book an appointment in the past"
        )
    
    # 4. Update the appointment with patient information
    try:
        update_query = text("""
            UPDATE gnuhealth_appointment
            SET patient = :patient_id,
                state = 'confirmed',
                write_date = :write_date,
                write_uid = :write_uid
            WHERE id = :appointment_id
        """)
        
        db.execute(update_query, {
            "patient_id": patient_id,
            "write_date": datetime.now(),
            "write_uid": user_id,
            "appointment_id": booking.appointment_id
        })
        
        # Get doctor info for the response
        doctor_query = text("""
            SELECT 
                pp.name AS doctor_name,
                ghp.specialty
            FROM gnuhealth_healthprofessional ghp
            JOIN party_party pp ON ghp.name = pp.id
            WHERE ghp.id = :healthprof_id
        """)
        
        doctor_info = db.execute(doctor_query, {"healthprof_id": slot[2]}).fetchone()
        
        db.commit()
        
        # Return success response with details
        return {
            "success": True,
            "message": "Appointment booked successfully",
            "appointment": {
                "id": booking.appointment_id,
                "appointment_date": appointment_date.strftime("%Y-%m-%d %H:%M:%S") if isinstance(appointment_date, datetime) else appointment_date,
                "doctor_name": doctor_info[0] if doctor_info else "Unknown",
                "specialty": doctor_info[1] if doctor_info else "Unknown",
                "status": "confirmed"
            }
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
