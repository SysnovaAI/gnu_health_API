import uuid
import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi.responses import JSONResponse
from ..models.base import get_db
import uvicorn
from typing import List
from datetime import datetime, timedelta, time
from .appointments import get_current_user

router = APIRouter()

class BookedDate(BaseModel):
    date: str

def get_patient(res_user_id, db: Session):
    patient = db.execute(text("""
            SELECT ghp.id
            FROM res_user AS ru
            INNER JOIN party_party AS pp ON pp.internal_user = ru.id AND pp.is_patient = TRUE
            INNER JOIN gnuhealth_patient AS ghp ON ghp.name = pp.id
            WHERE ru.id = :id;
        """), {"id": res_user_id}).fetchone()
    return patient


def get_booked_slot(patient, date, db: Session):
    patient_booked_info = db.execute(text("""
        select ga.id, ga.appointment_date, ga.appointment_type, pp.name, ga.state
        from gnuhealth_appointment ga 
        join gnuhealth_healthprofessional ghp on (ga.healthprof = ghp.id)
        join party_party pp on (ghp.name = pp.id)
        where patient = :patient and DATE(appointment_date) = :date
            
        """), {"patient": patient, "date": date}).fetchall()
    return patient_booked_info


@router.post("/patient-booked-slot")
def booked(request: BookedDate, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    #user = {"id": 27}
    patient = get_patient(user["id"], db)
    if patient:
        booked_slot = get_booked_slot(patient[0], request.date, db)
        print(booked_slot)
    
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
