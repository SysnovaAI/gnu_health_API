from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from datetime import datetime
from fastapi.security import OAuth2PasswordBearer
import uuid
from jose import jwt, JWTError
from ..models.base import get_db, SECRET_KEY

router = APIRouter()

# JWT Configuration
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    """Extracts the logged-in user's details from the JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")  # Ensure JWT payload contains 'id'
        role = payload.get("role")  # Get the role from the token
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found in token")
        return {"id": user_id, "role": role}  # Return both id and role

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token or expired session")




# Generate Unique Appointment Name
def generate_appointment_name():
    return f"APP {datetime.now().year}/{uuid.uuid4().hex[:6]}"

@router.post("/appointments_new")
def create_appointment(data: dict, request: Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user["id"]  # Get user ID from JWT

    required_fields = ["appointment_date", "healthprof"]
    if not all(field in data for field in required_fields):
        raise HTTPException(status_code=400, detail="Missing required fields")

    # Convert appointment_date to datetime and check if it's backdated
    try:
        appointment_datetime = datetime.strptime(data["appointment_date"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid appointment_date format. Use YYYY-MM-DD HH:MM:SS")

    if appointment_datetime < datetime.now():
        raise HTTPException(status_code=400, detail="Cannot book an appointment in the past")

    # Fetch `party_party.id` using `res_user.id`
    party_query = text("SELECT id FROM party_party WHERE internal_user = :user_id")
    party = db.execute(party_query, {"user_id": user_id}).fetchone()
    
    if not party:
        raise HTTPException(status_code=400, detail="User is not linked to a party entity")

    party_id = party.id  # Extract party ID

    # Fetch `gnuhealth_patient.id` using `party_party.id`
    patient_query = text("SELECT id FROM gnuhealth_patient WHERE name = :party_id")
    patient = db.execute(patient_query, {"party_id": party_id}).fetchone()
    
    if not patient:
        raise HTTPException(status_code=400, detail="User is not registered as a patient")

    patient_id = patient.id  # Extract patient ID

    # Check if an appointment is available for the given healthprof & date
    check_query = text("""
        SELECT id FROM gnuhealth_appointment 
        WHERE healthprof = :healthprof 
        AND appointment_date = :appointment_date 
        AND state = 'free'
    """)

    available_appointment = db.execute(check_query, {
        "healthprof": data["healthprof"],
        "appointment_date": data["appointment_date"]
    }).fetchone()

    if available_appointment:
        appointment_id = available_appointment.id

        # Update the patient field for the available appointment
        try:
            update_query = text("""
                UPDATE gnuhealth_appointment 
                SET patient = :patient, state = 'booked', write_date = :write_date, write_uid = :write_uid 
                WHERE id = :appointment_id
            """)

            db.execute(update_query, {
                "patient": patient_id,
                "write_date": datetime.now(),
                "write_uid": user_id,
                "appointment_id": appointment_id
            })

            db.commit()
            return {"success": True, "message": "Appointment booked successfully", "appointment_id": appointment_id}

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    else:
        return {"success": False, "message": "Appointment already booked"}



#  Create Appointment (Fixed)
@router.post("/appointments")
def create_appointment(data: dict, request: Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user["id"]  #  Get user ID from JWT

    required_fields = ["appointment_date", "appointment_type", "healthprof", "institution", "speciality"]
    if not all(field in data for field in required_fields):
        raise HTTPException(status_code=400, detail="Missing required fields")

    #  Fetch `party_party.id` using `res_user.id`
    party_query = text("SELECT id FROM party_party WHERE internal_user = :user_id")
    party = db.execute(party_query, {"user_id": user_id}).fetchone()
    
    if not party:
        raise HTTPException(status_code=400, detail="User is not linked to a party entity")

    party_id = party.id  #  Extract party ID

    #  Fetch `gnuhealth_patient.id` using `party_party.id`
    patient_query = text("SELECT id FROM gnuhealth_patient WHERE name = :party_id")
    patient = db.execute(patient_query, {"party_id": party_id}).fetchone()
    
    if not patient:
        raise HTTPException(status_code=400, detail="User is not registered as a patient")

    patient_id = patient.id  #  Extract patient ID

    appointment_name = generate_appointment_name()
    
    # Default values if not provided
    state = data.get("state", "free")
    urgency = data.get("urgency", "a")
    visit_type = data.get("visit_type", "general")

    try:
        query = text("""
            INSERT INTO gnuhealth_appointment 
            (appointment_date, appointment_type, create_date, create_uid, healthprof, institution, 
             name, patient, speciality, state, urgency, visit_type, write_date, write_uid) 
            VALUES (:appointment_date, :appointment_type, :create_date, :create_uid, :healthprof, :institution, 
                    :name, :patient, :speciality, :state, :urgency, :visit_type, NULL, :write_uid) 
            RETURNING id;
        """)

        result = db.execute(query, {
            "appointment_date": data["appointment_date"],
            "appointment_type": data["appointment_type"],
            "create_date": datetime.now(),
            "create_uid": user_id,
            "healthprof": data["healthprof"],
            "institution": data["institution"],
            "name": appointment_name,
            "patient": patient_id,  #  Correctly fetched patient ID
            "speciality": data["speciality"],
            "state": state,
            "urgency": urgency,
            "visit_type": visit_type,
            "write_uid": user_id
        }).fetchone()

        db.commit()
        return {"success": True, "appointment_id": result[0], "appointment_name": appointment_name}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")



@router.put("/appointments/{appointment_id}")
def update_appointment(
    appointment_id: int,
    data: dict,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    user_id = user["id"]  #  Get logged-in user ID

    #  Fetch `party_party.id` using `res_user.id`
    party_query = text("SELECT id FROM party_party WHERE internal_user = :user_id")
    party = db.execute(party_query, {"user_id": user_id}).fetchone()

    if not party:
        raise HTTPException(status_code=400, detail="User is not linked to a party entity")

    party_id = party.id  #  Extract party ID

    #  Check if User is a Patient
    patient_query = text("SELECT id FROM gnuhealth_patient WHERE name = :party_id")
    patient = db.execute(patient_query, {"party_id": party_id}).fetchone()

    if not patient:
        raise HTTPException(status_code=403, detail="Only patients can update appointments")

    patient_id = patient.id  #  Extract patient ID

    #  Fetch the Appointment to verify ownership
    appointment_query = text("""
        SELECT id, appointment_date, state FROM gnuhealth_appointment 
        WHERE id = :appointment_id AND patient = :patient_id
    """)
    appointment = db.execute(appointment_query, {"appointment_id": appointment_id, "patient_id": patient_id}).fetchone()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found or unauthorized access")

    #  Update Appointment Details
    new_date = data.get("appointment_date")
    new_state = data.get("state")  # e.g., "cancelled" or "confirmed"

    update_query = text("""
        UPDATE gnuhealth_appointment 
        SET appointment_date = COALESCE(:new_date, appointment_date),
            state = COALESCE(:new_state, state),
            write_date = :updated_at
        WHERE id = :appointment_id
    """)

    db.execute(update_query, {
        "appointment_id": appointment_id,
        "new_date": new_date,
        "new_state": new_state,
        "updated_at": datetime.now(),
    })

    db.commit()
    
    return {"success": True, "message": "Appointment updated successfully"}



@router.get("/appointments")
def get_appointments(request: Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user["id"]  # Get logged-in user ID from JWT

    # Check if the user is a patient
    patient_query = text("""
        SELECT gp.id AS patient_id
        FROM gnuhealth_patient gp
        JOIN party_party pp ON gp.name = pp.id
        WHERE pp.internal_user = :user_id
    """)
    
    patient = db.execute(patient_query, {"user_id": user_id}).fetchone()

    if patient:
        # User is a patient, fetch their appointments
        patient_id = patient.patient_id

        appointment_query = text("""
            SELECT 
                ga.id AS appointment_id,
                ga.appointment_date,
                ga.state AS status,
                ghp.id AS doctor_id,
                pp.name AS doctor_name,
                ghp.specialty
            FROM gnuhealth_appointment ga
            JOIN gnuhealth_healthprofessional ghp ON ga.healthprof = ghp.id
            JOIN party_party pp ON ghp.name = pp.id
            WHERE ga.patient = :patient_id
            ORDER BY ga.appointment_date DESC
        """)

        appointments = db.execute(appointment_query, {"patient_id": patient_id}).fetchall()

        if not appointments:
            return {"success": True, "message": "No appointments found", "appointments": []}

        return {
            "success": True,
            "appointments": [
                {
                    "appointment_id": appt.appointment_id,
                    "appointment_date": appt.appointment_date,
                    "status": appt.status,
                    "doctor_id": appt.doctor_id,
                    "doctor_name": appt.doctor_name,
                    "specialty": appt.specialty
                } for appt in appointments
            ]
        }

    # Check if the user is a doctor
    doctor_query = text("""
        SELECT id AS doctor_id FROM gnuhealth_healthprofessional WHERE name = (
            SELECT id FROM party_party WHERE internal_user = :user_id
        )
    """)

    doctor = db.execute(doctor_query, {"user_id": user_id}).fetchone()

    if doctor:
        # User is a doctor, fetch their appointments
        doctor_id = doctor.doctor_id

        appointment_query = text("""
            SELECT 
                ga.id AS appointment_id,
                ga.appointment_date,
                ga.state AS status,
                gp.id AS patient_id,
                pp.name AS patient_name
            FROM gnuhealth_appointment ga
            JOIN gnuhealth_patient gp ON ga.patient = gp.id
            JOIN party_party pp ON gp.name = pp.id
            WHERE ga.healthprof = :doctor_id
            ORDER BY ga.appointment_date DESC
        """)

        appointments = db.execute(appointment_query, {"doctor_id": doctor_id}).fetchall()

        if not appointments:
            return {"success": True, "message": "No appointments found", "appointments": []}

        return {
            "success": True,
            "appointments": [
                {
                    "appointment_id": appt.appointment_id,
                    "appointment_date": appt.appointment_date,
                    "status": appt.status,
                    "patient_id": appt.patient_id,
                    "patient_name": appt.patient_name
                } for appt in appointments
            ]
        }

    # If the user is neither a patient nor a doctor
    raise HTTPException(status_code=400, detail="User is neither a patient nor a doctor")