import uuid
import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi.responses import JSONResponse
from ..models.base import get_db
import uvicorn
from typing import List, Optional
from datetime import datetime, timedelta, time
from .appointments import get_current_user

router = APIRouter()

class BookedSlotRequest(BaseModel):
    date: Optional[str] = None

# Get patient ID based on user ID
def get_patient(res_user_id, db: Session):
    patient = db.execute(text("""
        SELECT ghp.id
        FROM res_user AS ru
        INNER JOIN party_party AS pp ON pp.internal_user = ru.id AND pp.is_patient = TRUE
        INNER JOIN gnuhealth_patient AS ghp ON ghp.name = pp.id
        WHERE ru.id = :id;
    """), {"id": res_user_id}).fetchone()
    return patient

# Get booked appointments for a patient (with or without date filter)
def get_booked_slot(patient, date: Optional[str], db: Session):
    if date:
        query = """
            SELECT ga.id, ga.appointment_date, ga.appointment_type, pp.name, ga.state
            FROM gnuhealth_appointment ga 
            JOIN gnuhealth_healthprofessional ghp ON ga.healthprof = ghp.id
            JOIN party_party pp ON ghp.name = pp.id
            WHERE ga.patient = :patient AND DATE(ga.appointment_date) = :date
        """
        params = {"patient": patient, "date": date}
    else:
        query = """
            SELECT ga.id, ga.appointment_date, ga.appointment_type, pp.name, ga.state
            FROM gnuhealth_appointment ga 
            JOIN gnuhealth_healthprofessional ghp ON ga.healthprof = ghp.id
            JOIN party_party pp ON ghp.name = pp.id
            WHERE ga.patient = :patient
        """
        params = {"patient": patient}

    return db.execute(text(query), params).fetchall()

# Endpoint to fetch booked slot(s)
@router.post("/patient-booked-slot")
def booked(request: BookedSlotRequest, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    patient = get_patient(user["id"], db)
    if patient:
        booked_slot = get_booked_slot(patient[0], request.date, db)

        available_slots = [
            {
                "id": row.id,
                "appointment_type": row.appointment_type,
                "appointment_date": row.appointment_date.strftime("%Y-%m-%d %H:%M:%S") if row.appointment_date else None,
                "state": row.state,
                "doctor_name": row.name
            } for row in booked_slot
        ]

        return JSONResponse(
            content={"message": available_slots},
            status_code=200
        )
    else:
        return JSONResponse(
            content={"message": "Patient is not Registered"},
            status_code=200
        )
