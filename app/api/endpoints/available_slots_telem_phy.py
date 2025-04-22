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
from ..models.send_email import send_email_notification
from .appointments import get_current_user

router = APIRouter()

class OnlineAppointment(BaseModel):
    id: int
    appointment_type: str

class CancelSlotAppointment(BaseModel):
    ids: List[int]

class CancelDateSlotAppointment(BaseModel):
    date: str

class ModifySlotAppointment(BaseModel):
    id: int
    date: str
    time: str

class ModifyDateSlotAppointment(BaseModel):
    start_date: str
    end_date: str
    start_time: str
    end_time: str
    duration: int
    cancel_date: str

class AppointmentRequest(BaseModel):
    appointment_type: str
    start_date: str
    end_date: str
    start_time: str
    end_time: str
    duration: int

class CheckSlotsRequest(BaseModel):
    appointment_type: Optional[str] = None
    appointment_date: Optional[str] = None
    state: Optional[str] = None

### Functions
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
    state= 'free'
    try:
        for slot in slots:
            db.execute(text("""
                INSERT INTO gnuhealth_appointment (appointment_date, appointment_type, healthprof,state) 
                VALUES (:appointment_date, :appointment_type, :healthprof, :state)
            """), {"appointment_date": slot, "appointment_type": appointment_type, "healthprof": health_professional, "state": state})
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        return False

def generate_doctor_appointment_slots(request) -> List[str]:
    start_date = datetime.strptime(request.start_date, "%Y-%m-%d").date()
    end_date = datetime.strptime(request.end_date, "%Y-%m-%d").date()
    
    start_time = datetime.strptime(request.start_time, "%I:%M %p").time()
    end_time = datetime.strptime(request.end_time, "%I:%M %p").time()
    
    slots = []
    current_date = start_date

    while current_date <= end_date:
        if start_time < end_time:
            current_datetime = datetime.combine(current_date, start_time)
            end_datetime = datetime.combine(current_date, end_time)
            while current_datetime < end_datetime:
                slots.append(current_datetime.strftime("%Y-%m-%d %I:%M %p"))
                current_datetime += timedelta(minutes=request.duration)
        else:
            current_datetime = datetime.combine(current_date, start_time)
            midnight = datetime.combine(current_date + timedelta(days=1), time(0, 0))
            while current_datetime < midnight:
                slots.append(current_datetime.strftime("%Y-%m-%d %I:%M %p"))
                current_datetime += timedelta(minutes=request.duration)
            
            if current_date < end_date:
                next_day = current_date + timedelta(days=1)
                current_datetime = datetime.combine(next_day, time(0, 0))
                end_datetime = datetime.combine(next_day, end_time)
                while current_datetime < end_datetime:
                    slots.append(current_datetime.strftime("%Y-%m-%d %I:%M %p"))
                    current_datetime += timedelta(minutes=request.duration)
        current_date += timedelta(days=1)
    
    return slots

def date_slots_modify(healthprof, slots, cancel_date, db: Session):
    cancel_date = datetime.strptime(cancel_date, "%Y-%m-%d").date()
       
    existing_slots = db.execute(text("""
        SELECT appointment_date
        FROM gnuhealth_appointment 
        WHERE healthprof = :healthprof
    """), {
        "healthprof": healthprof
    }).fetchall()

    modification_slot = db.execute(text("""
        SELECT appointment_date, id, patient, state 
        FROM gnuhealth_appointment 
        WHERE healthprof = :healthprof 
            AND DATE(appointment_date) = :cancel_date
    """), {
        "healthprof": healthprof,
        "cancel_date": cancel_date  # Format should be 'YYYY-MM-DD'
    }).fetchall()

    existing_slots_set = set(slot[0].strftime("%Y-%m-%d %H:%M:%S") for slot in existing_slots)
    id_list = [row[1] for row in modification_slot]
    patient_list = [row[2] for row in modification_slot]
    state_list = [row[3] for row in modification_slot]

    doctor_email = db.execute(text("""
        SELECT res_user.email
        FROM gnuhealth_healthprofessional AS hp
        INNER JOIN party_party AS pp ON pp.id = hp.name
        INNER JOIN res_user ON res_user.id = pp.internal_user
        WHERE hp.id = :id;
    """), {"id": healthprof}).fetchone()
    
    # Insert only non-existing slots
    new_slots = [slot for slot in slots if slot not in existing_slots_set]

    if new_slots:
        for slot, id, patient, state in zip(new_slots, id_list, patient_list, state_list):
            update_query = text("""
                UPDATE gnuhealth_appointment 
                SET appointment_date = :appointment_date, state = :state
                WHERE id = :appointment_id
            """)
            db.execute(update_query, {
                "appointment_id": id,
                "appointment_date": slot,
                "state": "free"
            })

            db.commit()

            if state == 'booked':
                patient_email = db.execute(text("""
                    SELECT res_user.email
                    FROM gnuhealth_patient AS ghp
                    INNER JOIN party_party AS pp ON pp.id = ghp.name
                    INNER JOIN res_user ON res_user.id = pp.internal_user
                    WHERE ghp.id = :id;
                """), {"id": patient}).fetchone()
                #send_email_notification(doctor_email[0], "Change", "Your appointment Date is Changed")
                #send_email_notification(patient_email[0], "Change", "Do you want to get your payment back or reschedule the appointment?")
            else:
                pass
                #send_email_notification(doctor_email[0], "Change", "Your appointment Date is Changed")

            
    else:
        return False
    

def slots_modify(id, date, time, db: Session):
    user = db.execute(text("""
        SELECT healthprof, state, patient
        FROM gnuhealth_appointment 
        WHERE id = :id;
    """), {"id": id}).fetchone()

    state_status = db.execute(text("""
        SELECT appointment_date, state, id
        FROM gnuhealth_appointment 
        WHERE healthprof = :healthprof;
    """), {"healthprof": user[0]}).fetchall()

    # Convert the datetime to a string formatted as 'YYYY-MM-DD'
    date_list = [row[0].strftime("%Y-%m-%d") for row in state_status]
    time_list =  [row[0].strftime("%I:%M %p") for row in state_status]
    state_list = [row[1] for row in state_status]
    id_list = [row[2] for row in state_status]
    matching_date = [(d, t, s, id) for d, t, s, id in zip(date_list, time_list, state_list, id_list) if (d == date and t == time)]
    if matching_date and matching_date[0][2] in ("booked", "free"):
        return False
    else:
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        time_obj = datetime.strptime(time, "%I:%M %p").time()
        appointment_date = datetime.combine(date_obj, time_obj)
        instant_time = datetime.now()

        print("appointment_date: ", appointment_date, "instant_time : ", instant_time)
        if appointment_date <= instant_time:
            return False
        
        update_query = text("""
            UPDATE gnuhealth_appointment 
            SET appointment_date = :appointment_date,
                state = :state
            WHERE id = :appointment_id
        """)

        db.execute(update_query, {
            "appointment_id": id,
            "appointment_date": appointment_date,
            "state": "free"  # Make sure this variable is defined
        })

        db.commit()


        healthprof_id = user[0]
        state = user[1]
        patient_id = user[2]

        doctor_email = db.execute(text("""
            SELECT res_user.email
            FROM gnuhealth_healthprofessional AS hp
            INNER JOIN party_party AS pp ON pp.id = hp.name
            INNER JOIN res_user ON res_user.id = pp.internal_user
            WHERE hp.id = :id;
        """), {"id": healthprof_id}).fetchone()

        if state == 'booked':
            patient_email = db.execute(text("""
                SELECT res_user.email
                FROM gnuhealth_patient AS ghp
                INNER JOIN party_party AS pp ON pp.id = ghp.name
                INNER JOIN res_user ON res_user.id = pp.internal_user
                WHERE ghp.id = :id;
            """), {"id": patient_id}).fetchone()

            #send_email_notification(doctor_email[0], state, f"Your appointment is {state}")
            #send_email_notification(patient_email[0], state, "Do you want to get your payment back or reschedule the appointment?")
        
        else:
            pass
            #send_email_notification(doctor_email[0], state, f"Your appointment is {state}")

def date_slots_cancel(healthprof, state, date_to_match, db: Session):
    state_status = db.execute(text("""
        SELECT appointment_date, state, id
        FROM gnuhealth_appointment 
        WHERE healthprof = :healthprof;
    """), {"healthprof": healthprof}).fetchall()

    # Convert the datetime to a string formatted as 'YYYY-MM-DD'
    date_time = [row[0].strftime("%Y-%m-%d") for row in state_status]
    state_list = [row[1] for row in state_status]
    id_list = [row[2] for row in state_status]
    matching_date = [(d, s, id) for d, s, id in zip(date_time, state_list, id_list) if d == date_to_match]

    for _, appointment_state, id in matching_date:
        doctor_email = db.execute(text("""
            SELECT res_user.email
            FROM gnuhealth_healthprofessional AS hp
            INNER JOIN party_party AS pp ON pp.id = hp.name
            INNER JOIN res_user ON res_user.id = pp.internal_user
            WHERE hp.id = :id;
        """), {"id": healthprof}).fetchone()

        if appointment_state == "booked":
            patient_id = db.execute(text("""
                SELECT patient 
                FROM gnuhealth_appointment 
                WHERE id = :id;
            """), {"id": id}).fetchone()

            patient_email = db.execute(text("""
                SELECT res_user.email
                FROM gnuhealth_patient AS ghp
                INNER JOIN party_party AS pp ON pp.id = ghp.name
                INNER JOIN res_user ON res_user.id = pp.internal_user
                WHERE ghp.id = :id;
            """), {"id": patient_id[0]}).fetchone()
            update_state(id, state, db)
            #send_email_notification(doctor_email[0], state, f"Your appointment is {state}")
            #send_email_notification(patient_email[0], state, "Do you want to get your payment back or reschedule the appointment?")

        else:
            update_state(id, state, db)
            #send_email_notification(doctor_email[0], state, f"Your appointment is {state}")


def update_appointment_status(id: int, appointment_type: str, db: Session):
    update_query = text("""
        UPDATE gnuhealth_appointment 
        SET appointment_type = :appointment_type
        WHERE id = :appointment_id
    """)

    db.execute(update_query, {
        "appointment_id": id,
        "appointment_type": appointment_type,
    })

    db.commit()


def update_state(id: int, state: str, db: Session):
    update_query = text("""
        UPDATE gnuhealth_appointment 
        SET state = :state
        WHERE id = :appointment_id
    """)

    db.execute(update_query, {
        "appointment_id": id,
        "state": state,
    })

    db.commit()

def slot_cancel(id, state, db: Session):
    print(id)
    state_status_result = db.execute(text("""
        SELECT state 
        FROM gnuhealth_appointment 
        WHERE id = :id;
    """), {"id": id}).fetchone()

    if not state_status_result:
        raise HTTPException(status_code=404, detail=f"Appointment with id {id} not found")

    state_status = state_status_result[0]

    user = db.execute(text("""
        SELECT healthprof, patient 
        FROM gnuhealth_appointment 
        WHERE id = :id;
    """), {"id": id}).fetchone()

    if not user:
        raise HTTPException(status_code=404, detail=f"User data for appointment id {id} not found")

    healthprof_id = user[0]
    patient_id = user[1]

    doctor_email = db.execute(text("""
        SELECT res_user.email
        FROM gnuhealth_healthprofessional AS hp
        INNER JOIN party_party AS pp ON pp.id = hp.name
        INNER JOIN res_user ON res_user.id = pp.internal_user
        WHERE hp.id = :id;
    """), {"id": healthprof_id}).fetchone()

    if not doctor_email:
        raise HTTPException(status_code=404, detail=f"Doctor email for health professional {healthprof_id} not found")

    if state_status == 'booked':
        patient_email = db.execute(text("""
            SELECT res_user.email
            FROM gnuhealth_patient AS ghp
            INNER JOIN party_party AS pp ON pp.id = ghp.name
            INNER JOIN res_user ON res_user.id = pp.internal_user
            WHERE ghp.id = :id;
        """), {"id": patient_id}).fetchone()

        if not patient_email:
            raise HTTPException(status_code=404, detail=f"Patient email for patient {patient_id} not found")

        update_state(id, state, db)
        #send_email_notification(doctor_email[0], state, f"Your appointment is {state}")
        #send_email_notification(patient_email[0], state, "Do you want to get your payment back or reschedule the appointment?")
    else:
        update_state(id, state, db)
        #send_email_notification(doctor_email[0], state, f"Your appointment is {state}")



def get_doctor_slots(doctor_id, db: Session):
    slots= db.execute(text("""
        SELECT id, appointment_date 
        FROM gnuhealth_appointment 
        WHERE healthprof = :doctor_id 
        ORDER BY appointment_date;
    """), {"doctor_id": doctor_id}).fetchall()
    # return [slot[0].strftime("%Y-%m-%d %I:%M %p") for slot in slots]
    return [
    {"id": slot_id, "slot": appointment_date.strftime("%Y-%m-%d %I:%M %p")} for slot_id, appointment_date in slots
    ]


def get_healthprof(res_user_id, db: Session):
    healthprof = db.execute(text("""
            SELECT ghp.id
            FROM res_user AS ru
            INNER JOIN party_party AS pp ON pp.internal_user = ru.id
            INNER JOIN gnuhealth_healthprofessional AS ghp ON ghp.name = pp.id
            WHERE ru.id = :id;
        """), {"id": res_user_id}).fetchone()
    return healthprof

@router.post("/generate-slots")
def get_slots(request: AppointmentRequest, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    # Get current datetime
    current_datetime = datetime.now()

    start_datetime = datetime.strptime(f"{request.start_date} {request.start_time}", "%Y-%m-%d %I:%M %p")
    end_datetime = datetime.strptime(f"{request.end_date} {request.end_time}", "%Y-%m-%d %I:%M %p")

    if start_datetime > end_datetime:
        return JSONResponse(content={"message": "Invalid date time"}, status_code=400)
    # Check if the start or end datetime is in the past
    if start_datetime < current_datetime or end_datetime < current_datetime:
        return JSONResponse(content={"message": "Your time cannot be in the past"}, status_code=400)
    
    if not id_is_present(user["id"], db):
        return JSONResponse(content={"message": "User Not Verified"}, status_code=400)

    result = party_party(user["id"], db)
    if not result:
        return JSONResponse(content={"message": "Not a Health Professional"}, status_code=400)

    if result[1]:  # Checking if is_healthprof is True
        user_status = user_is_doctor(result[0], db)
        if user_status:
  
            new_slots = generate_doctor_appointment_slots(request)
            
            doctor_health_prof_id = get_healthprof(user["id"], db)
            
            existing_slot = get_doctor_slots(doctor_health_prof_id[0], db)
            existing_slots_list = [slot['slot'] for slot in existing_slot]

            # Check if any of the new_slots exist in existing_slot_set
            unique_new_slots = [slot for slot in new_slots if slot not in existing_slots_list]

            if unique_new_slots:
                success = insert_appointments(user_status, request.appointment_type, unique_new_slots, db)
                return JSONResponse(content={"message": f"Your {len(unique_new_slots)} slots appointments successfully inserted from {len(new_slots)} slots" if success else "Failed to insert appointments"}, status_code=200)
            else:
                return JSONResponse(content={"message": "These slots already exist"}, status_code=200)
        return JSONResponse(content={"message": "Not present in the gnuhealth_healthprofessional Database"}, status_code=400)
    
    return JSONResponse(content={"message": "Not a Health Professional"}, status_code=400)

@router.post("/check-available-slots")
def check_slots(
    request: CheckSlotsRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    try:
        # Get health professional ID from session
        healthprof = get_healthprof(user["id"], db)
        if not healthprof:
            return JSONResponse(
                content={"message": "No health professional found for the current user"},
                status_code=404
            )
        health_prof_id = healthprof[0]

        # Start building the query
        query = """
            SELECT 
                id, 
                appointment_date, 
                appointment_type, 
                state
            FROM gnuhealth_appointment 
            WHERE healthprof = :health_prof_id
        """
        
        params = {"health_prof_id": health_prof_id}

        # Add state filter if provided
        if request.state:
            query += " AND state = :state"
            params["state"] = request.state

        # Add appointment type filter if provided
        if request.appointment_type:
            query += " AND appointment_type = :appointment_type"
            params["appointment_type"] = request.appointment_type

        # Add date filter if provided
        if request.appointment_date:
            try:
                # Convert string date to datetime object
                date_obj = datetime.strptime(request.appointment_date, "%Y-%m-%d").date()
                query += " AND DATE(appointment_date) = :appointment_date"
                params["appointment_date"] = date_obj
            except ValueError:
                return JSONResponse(
                    content={"message": "Invalid date format. Please use YYYY-MM-DD"},
                    status_code=400
                )

        # Execute the query
        slots = db.execute(text(query), params).fetchall()
        
        if not slots:
            return JSONResponse(
                content={"message": "No slots available for this doctor"},
                status_code=404
            )
        
        # Format the response
        formatted_slots = [
            {
                "id": slot.id,
                "slot": slot.appointment_date.strftime("%Y-%m-%d %I:%M %p"),
                "appointment_type": slot.appointment_type,
                "state": slot.state
            } for slot in slots
        ]
        
        return JSONResponse(
            content={
                "slots": formatted_slots
            },
            status_code=200
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Error occurred: {str(e)}"},
            status_code=500
        )


@router.post("/slot-telemedicine-physical")
def appointment_status(request: OnlineAppointment, db: Session = Depends(get_db)):
    update_appointment_status(request.id, request.appointment_type, db)
    return JSONResponse(
        content={"message": "Success"},
        status_code=200
    )

@router.post("/specific-slot-cancel")
def cancel_slot(request: CancelSlotAppointment, db: Session = Depends(get_db)):
    state = "Cancel"
    for id in request.ids:
        slot_cancel(id, state, db)
    return JSONResponse(
        content={"message": "Slot State Cancel"},
        status_code=200
    )

@router.post("/date-slot-cancel")
def date_slot_cancel(request: CancelDateSlotAppointment, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    healthprof = get_healthprof(user["id"], db)
    print(healthprof)
    state = "Cancel"
    date_slots_cancel(healthprof[0], state, request.date, db)
    return JSONResponse(
        content={"message": "Slot State Cancel"},
        status_code=200
    )


@router.post("/specific-slot-modification")
def slot_modify(request: ModifySlotAppointment, db: Session = Depends(get_db)):
    res = slots_modify(request.id, request.date, request.time, db)
    if res == False:
        return JSONResponse(
        content={"message": "Slot is not Available"},
        status_code=200
    )
    else:
        return JSONResponse(
            content={"message": "Slot State Modify Based on Specific time"},
            status_code=200
        )


@router.post("/date-slot-modification")
def date_slot_modify(request: ModifyDateSlotAppointment, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    healthprof = get_healthprof(user["id"], db)
    slots = generate_doctor_appointment_slots(request)
    res = date_slots_modify(healthprof[0], slots, request.cancel_date, db)
    if res == False:
        return JSONResponse(
        content={"message": "Slot is not Available"},
        status_code=200
    )
    else:
        return JSONResponse(
            content={"message": "Slot State Modify based on Date"},
            status_code=200
        )

if __name__ == "__main__":
    uvicorn.run(router, host="127.0.0.1", port=8001)


