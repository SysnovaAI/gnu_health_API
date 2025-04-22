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

class AvailableSlorDoctor(BaseModel):
    date: str

def get_doctor(res_user_id, db: Session):
    doctor = db.execute(text("""
            SELECT ghp.id
            FROM res_user AS ru
            INNER JOIN party_party AS pp ON pp.internal_user = ru.id AND pp.is_healthprof = TRUE
            INNER JOIN gnuhealth_healthprofessional AS ghp ON ghp.name = pp.id
            WHERE ru.id = :id;
        """), {"id": res_user_id}).fetchone()
    return doctor


def get_booked_slot(doctor, date, db: Session):
    doctor_booked_info = db.execute(text("""
        select ga.id, ga.appointment_date, ga.appointment_type, ga.state
        from gnuhealth_appointment ga 
        where ga.healthprof = :doctor and DATE(ga.appointment_date) = :date and ga.state != 'Cancel'
            
        """), {"doctor": doctor, "date": date}).fetchall()
    return doctor_booked_info


@router.post("/doctor-available-slot-date")
def booked(request: AvailableSlorDoctor, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    doctor = get_doctor(user["id"], db)
    if doctor:
        booked_slot = get_booked_slot(doctor[0], request.date, db)
    
        available_slots = [
            {
            "id": row.id, 
            "appointment_type": row.appointment_type,
            "appointment_date": row.appointment_date.strftime("%Y-%m-%d %H:%M:%S") if row.appointment_date else None,
            "state": row.state,
            
            } for row in booked_slot
            ]
        
        return JSONResponse(
            content={"message": available_slots},
            status_code=200
        )
    else:
        return JSONResponse(
            content={"message": "Doctor is not Registered"},
            status_code=200
        )
