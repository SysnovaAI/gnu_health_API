from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from datetime import datetime
from fastapi.security import OAuth2PasswordBearer
from ..models.base import get_db
from pydantic import BaseModel
from .appointments import get_current_user

router = APIRouter()

# Pydantic model for request validation
class AppointmentCancelRequest(BaseModel):
    appointment_id: int

@router.post("/request-appointment-cancellation")
def request_appointment_cancellation(
    request: AppointmentCancelRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)  # This will be imported from appointments.py
):
    user_id = user["id"]  # Get user ID from JWT

    # First verify if the user is a patient
    party_query = text("""
        SELECT pp.id 
        FROM party_party pp 
        WHERE pp.internal_user = :user_id
    """)
    party = db.execute(party_query, {"user_id": user_id}).fetchone()
    
    if not party:
        raise HTTPException(status_code=400, detail="User is not linked to a party entity")

    party_id = party[0]

    # Verify if user is a patient
    patient_query = text("""
        SELECT id 
        FROM gnuhealth_patient 
        WHERE name = :party_id
    """)
    patient = db.execute(patient_query, {"party_id": party_id}).fetchone()
    
    if not patient:
        raise HTTPException(status_code=403, detail="Only patients can request appointment cancellation")

    patient_id = patient[0]

    # Verify if the appointment exists and belongs to this patient
    appointment_query = text("""
        SELECT id, state 
        FROM gnuhealth_appointment 
        WHERE id = :appointment_id 
        AND patient = :patient_id
    """)
    
    appointment = db.execute(appointment_query, {
        "appointment_id": request.appointment_id,
        "patient_id": patient_id
    }).fetchone()

    if not appointment:
        raise HTTPException(
            status_code=404, 
            detail="Appointment not found or does not belong to this patient"
        )

    if appointment[1] != "confirmed":
        raise HTTPException(
            status_code=400, 
            detail="Only confirmed appointments can be requested for cancellation"
        )

    try:
        # Update the appointment state to "cancel request"
        update_query = text("""
            UPDATE gnuhealth_appointment 
            SET state = 'cancel request',
                write_date = :write_date,
                write_uid = :write_uid
            WHERE id = :appointment_id
        """)

        db.execute(update_query, {
            "appointment_id": request.appointment_id,
            "write_date": datetime.now(),
            "write_uid": user_id
        })

        db.commit()
        return {
            "success": True,
            "message": "Appointment cancellation request submitted successfully"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
