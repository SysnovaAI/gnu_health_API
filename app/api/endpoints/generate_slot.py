import uuid
import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi.responses import JSONResponse
from ..models.base import get_db

router = APIRouter()

class AppointmentRequest(BaseModel):
    id: int
    appointment_type: str
    start_date: str
    end_date: str
    start_time: str
    end_time: str
    duration: int

def id_is_present(user_id: int, db: Session):
    result = db.execute(text("SELECT id FROM res_user WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    return result is not None

def party_party(user_id: int, db: Session):
    result = db.execute(text("SELECT id, is_healthprof FROM party_party WHERE internal_user = :user_id"), {"user_id": user_id}).fetchone()
    return result if result else None

def user_is_doctor(user_id: int, db: Session):
    result = db.execute(text("SELECT id FROM gnuhealth_healthprofessional WHERE name = :user_id"), {"user_id": user_id}).fetchone()
    return result[0] if result else None

def insert_appointments(health_professional: int, appointment_type: str, slots: list, db: Session):
    try:
        for slot in slots:
            db.execute(text("""
                INSERT INTO gnuhealth_appointment (appointment_date, appointment_type, healthprof) 
                VALUES (:appointment_date, :appointment_type, :healthprof)
            """), {"appointment_date": slot, "appointment_type": appointment_type, "healthprof": health_professional})
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        return False

def generate_appointment_slots(request: AppointmentRequest) -> list:
    start_date = datetime.datetime.strptime(request.start_date, "%Y-%m-%d").date()
    end_date = datetime.datetime.strptime(request.end_date, "%Y-%m-%d").date()
    
    start_time = datetime.datetime.strptime(request.start_time, "%I:%M %p").time()
    end_time = datetime.datetime.strptime(request.end_time, "%I:%M %p").time()
    
    slots = []
    current_date = start_date

    while current_date <= end_date:
        if start_time < end_time:
            current_datetime = datetime.datetime.combine(current_date, start_time)
            end_datetime = datetime.datetime.combine(current_date, end_time)
            while current_datetime < end_datetime:
                slots.append(current_datetime.strftime("%Y-%m-%d %H:%M:%S"))
                current_datetime += datetime.timedelta(minutes=request.duration)
        current_date += datetime.timedelta(days=1)
    
    return slots

@router.post("/generate-slots")
def get_slots(request: AppointmentRequest, db: Session = Depends(get_db)):
    if not id_is_present(request.id, db):
        return JSONResponse(content={"message": "User Not Verified"}, status_code=400)

    result = party_party(request.id, db)
    if not result:
        return JSONResponse(content={"message": "Not a Health Professional"}, status_code=400)

    if result[1]:  # Checking if is_healthprof is True
        user_status = user_is_doctor(result[0], db)
        if user_status:
            slots = generate_appointment_slots(request)
            success = insert_appointments(user_status, request.appointment_type, slots, db)
            return JSONResponse(content={"message": "Appointments successfully inserted" if success else "Failed to insert appointments"}, status_code=200)
        return JSONResponse(content={"message": "Not present in the gnuhealth_healthprofessional Database"}, status_code=400)
    
    return JSONResponse(content={"message": "Not a Health Professional"}, status_code=400)
