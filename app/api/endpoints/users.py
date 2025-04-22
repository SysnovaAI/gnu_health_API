import uuid
import hashlib
import random
import string
import jwt
import os
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64
from passlib.context import CryptContext
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from ..models.base import get_db  # Import database session
from passlib.context import CryptContext
from dotenv import load_dotenv
load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter()

# Mapping user types to table columns
allowed_types = {
    "patients": "is_patient",
    "doctors": "is_healthprof",
    "institutions": "is_institution",
    "pharmacies": "is_pharmacy",
    "insurance_companies": "is_insurance_company"
}

@router.get("/available-slots/{doc_id}")
def get_all_available_slots(doc_id: int, db: Session = Depends(get_db)):
    """
    Fetch all available (free) appointment slots for a specific doctor.
    """
    try:
        slots_query = text("""
            SELECT
                appointment_date,id,healthprof,
                state AS status,
                appointment_type
            FROM gnuhealth_appointment
            WHERE healthprof = :doc_id AND state = 'free'
            ORDER BY appointment_date ASC
        """)

        results = db.execute(slots_query, {"doc_id": doc_id}).fetchall()

        available_slots = [
            {
                "appointment_date": row.appointment_date.strftime("%Y-%m-%d %H:%M:%S") if row.appointment_date else None,
                "status": row.status,
                "appointment_type": row.appointment_type,
                "doctor_id": row.healthprof,
                "slot_id":row.id
            } for row in results
        ]

        if not available_slots:
            return {
                "success": False,
                "message": "No available slots found for this doctor.",
                "slots": []
            }

        return {
            "success": True,
            "message": f"Available slots for doctor ID {doc_id}",
            "slots": available_slots
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching slots: {str(e)}")




@router.get("/all-users")
def get_all_users(db: Session = Depends(get_db)):
    """ Fetch all users with their respective types """
    query = text("""
        SELECT *,
        CASE 
            WHEN is_patient THEN 'patient'
            WHEN is_healthprof THEN 'doctor'
            WHEN is_institution THEN 'institution'
            WHEN is_pharmacy THEN 'pharmacy'
            WHEN is_insurance_company THEN 'insurance_company'
            ELSE 'unknown'
        END AS user_type
        FROM public.party_party
    """)

    result = db.execute(query).fetchall()
    
    return {"data": [dict(row._mapping) for row in result]}


allowed_types = {
    "doctor": "is_healthprof",
    "patient": "is_patient"
}


@router.get("/{user_type}")
def get_users(user_type: str, db: Session = Depends(get_db)):
    """Fetch detailed users dynamically based on type (doctor/patient)"""
    if user_type not in USER_TYPES:
        raise HTTPException(status_code=400, detail="Invalid user type")

    if user_type == "doctor":
        query = text("""
            SELECT 
                ghp.id AS healthprof_id,
                pp.name AS full_name,
                pp.gender,
                pp.mobile_number AS phone_number,
                rs.name AS specialty,
                gdu.address_city, gdu.address_municipality, gdu.address_street, 
                gdu.address_street_bis, gdu.address_street_number, gdu.address_zip,
                ru.login AS username, ru.email
            FROM gnuhealth_healthprofessional ghp
            JOIN party_party pp ON ghp.name = pp.id
            LEFT JOIN gnuhealth_hp_specialty ghps ON ghps.name = ghp.id
            LEFT JOIN gnuhealth_specialty rs ON rs.id = ghps.specialty
            LEFT JOIN gnuhealth_du gdu ON pp.du = gdu.id
            LEFT JOIN res_user ru ON pp.internal_user = ru.id
            WHERE pp.is_healthprof = true
        """)

    elif user_type == "patient":
        query = text("""
            SELECT 
                gp.id AS patient_id,
                pp.name AS full_name,
                pp.gender,
                pp.mobile_number AS phone_number,
                gdu.address_city, gdu.address_municipality, gdu.address_street, 
                gdu.address_street_bis, gdu.address_street_number, gdu.address_zip,
                ru.login AS username, ru.email
            FROM gnuhealth_patient gp
            JOIN party_party pp ON gp.name = pp.id
            LEFT JOIN gnuhealth_du gdu ON pp.du = gdu.id
            LEFT JOIN res_user ru ON pp.internal_user = ru.id
            WHERE pp.is_patient = true
        """)

    result = db.execute(query).fetchall()
    return {"data": [dict(row._mapping) for row in result]}



@router.get("/{user_type}/{id}")
def get_single_user(user_type: str, id: int, db: Session = Depends(get_db)):
    """Fetch a single user dynamically based on type (doctor/patient)"""

    if user_type not in USER_TYPES:
        raise HTTPException(status_code=400, detail="Invalid user type")

    if user_type == "doctor":
        query = text("""
            SELECT 
                ghp.id AS healthprof_id,
                pp.name AS full_name,
                pp.gender,
                pp.mobile_number AS phone_number,
                rs.name AS specialty,
                gdu.address_city, gdu.address_municipality, gdu.address_street, 
                gdu.address_street_bis, gdu.address_street_number, gdu.address_zip,
                ru.login AS username, ru.email
            FROM gnuhealth_healthprofessional ghp
            JOIN party_party pp ON ghp.name = pp.id
            LEFT JOIN gnuhealth_hp_specialty ghps ON ghps.name = ghp.id
            LEFT JOIN gnuhealth_specialty rs ON rs.id = ghps.specialty
            LEFT JOIN gnuhealth_du gdu ON pp.du = gdu.id
            LEFT JOIN res_user ru ON pp.internal_user = ru.id
            WHERE ghp.id = :id AND pp.is_healthprof = true
            LIMIT 1
        """)

    elif user_type == "patient":
        query = text("""
            SELECT 
                gp.id AS patient_id,
                pp.name AS full_name,
                pp.gender,
                pp.mobile_number AS phone_number,
                gdu.address_city, gdu.address_municipality, gdu.address_street, 
                gdu.address_street_bis, gdu.address_street_number, gdu.address_zip,
                ru.login AS username, ru.email
            FROM gnuhealth_patient gp
            JOIN party_party pp ON gp.name = pp.id
            LEFT JOIN gnuhealth_du gdu ON pp.du = gdu.id
            LEFT JOIN res_user ru ON pp.internal_user = ru.id
            WHERE gp.id = :id AND pp.is_patient = true
            LIMIT 1
        """)

    result = db.execute(query, {"id": id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="User not found")

    return {"data": dict(result._mapping)}
    



# User types and their respective flags
USER_TYPES = {
    "doctor": {"is_healthprof": True, "is_patient": False},
    "patient": {"is_healthprof": False, "is_patient": True}
}

def generate_code(name):
    """Generate a unique code using UUID prefix + name"""
    return f"{uuid.uuid4().hex[:8]}-{name}"  # Example: E94F9C08-Dr. Rabi Test


def hash_password(password: str) -> str:
    return pwd_context.hash(password)  

def generate_ref():
    """Generate a 9-character alphanumeric reference code"""
    STRSIZE = 9
    puid = ""
    for x in range(STRSIZE):
        puid += random.choice(string.ascii_uppercase if (x < 3 or x > 5) else string.digits)
    return puid

@router.post("/{user_type}/register")
def register_user(user_type: str, data: dict, db: Session = Depends(get_db)):
    """ Register a new user dynamically (Doctor/Patient) """
    if user_type not in USER_TYPES:
        raise HTTPException(status_code=400, detail="Invalid user type")

    # Extract required fields
    name = data.get("name")
    user_name = data.get("user_name")
    mobile_number = data.get("mobile_number")
    email = data.get("email")
    password_hash = data.get("password_hash")
    gender = data.get("gender", "").lower()  # Ensure lowercase
    year_of_experience = data.get("year_of_experience") if user_type == "doctor" else None

    if not all([name, mobile_number, email, password_hash]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    # Hash the password
    hashed_password = hash_password(password_hash)
    generated_code = generate_code(name)
    reference_code = generate_ref()

    # Gender conversion
    gender_value = "m" if gender == "male" else "f" if gender == "female" else None

    try:
        # Step 1: Insert into `res_user` table
        user_query = text("""
            INSERT INTO res_user (login, password_hash, email, menu, name) 
            VALUES (:user_name, :password_hash, :email, :menu, :name) RETURNING id;
        """)
        user_result = db.execute(user_query, {
            "user_name": user_name,
            "name": name,  # Both `login` and `name` now store `name`
            "password_hash": hashed_password,
            "email": email,
            "menu": 1  # Ensure it's a valid integer
        }).fetchone()

        if not user_result:
            raise HTTPException(status_code=500, detail="Failed to create user")

        user_id = user_result[0]  # Get generated user ID

        # Step 2: Insert into `party_party` table
        party_query = text("""
            INSERT INTO party_party (name, mobile_number, internal_user, is_healthprof, is_patient, is_person, code, active, create_date, create_uid, write_date, write_uid, activation_date, gender, ref) 
            VALUES (:name, :mobile_number, :user_id, :is_healthprof, :is_patient, :is_person, :code, :active, :create_date, :create_uid, :write_date, :write_uid, :activation_date, :gender, :ref) RETURNING id;
        """)
        party_result = db.execute(party_query, {
            "name": name,
            "mobile_number": mobile_number,
            "user_id": user_id,
            "is_healthprof": USER_TYPES[user_type]["is_healthprof"],
            "is_patient": USER_TYPES[user_type]["is_patient"],
            "is_person": True,
            "code": generated_code,
            "active": True,
            "create_date": datetime.now(),
            "create_uid": 1,
            "write_date": datetime.now(),
            "write_uid": 1,
            "activation_date": datetime.now().strftime("%Y-%m-%d"),
            "gender": gender_value,
            "ref": reference_code
        }).fetchone()

        if not party_result:
            raise HTTPException(status_code=500, detail="Failed to create party record")

        party_id = party_result[0]

        # Step 3: Insert into `gnuhealth_healthprofessional` if user is a doctor
        if user_type == "doctor":
            health_professional_query = text("""
                INSERT INTO gnuhealth_healthprofessional (active, create_date, create_uid, name, year_of_experience) 
                VALUES (:active, :create_date, :create_uid, :name, :year_of_experience) RETURNING id;
            """)
            health_prof_result = db.execute(health_professional_query, {
                "active": True,
                "create_date": datetime.now(),
                "create_uid": 1,
                "name": party_id,  # Reference `party_party.id`
                "year_of_experience": year_of_experience
            }).fetchone()

            if not health_prof_result:
                raise HTTPException(status_code=500, detail="Failed to create health professional record")

            health_prof_id = health_prof_result[0]

        # Step 4: Insert into `gnuhealth_patient` if user is a patient
        elif user_type == "patient":
            patient_query = text("""
                INSERT INTO gnuhealth_patient (active, create_date, create_uid, name) 
                VALUES (:active, :create_date, :create_uid, :name) RETURNING id;
            """)
            patient_result = db.execute(patient_query, {
                "active": True,
                "create_date": datetime.now(),
                "create_uid": 1,
                "name": party_id  # Reference `party_party.id`
            }).fetchone()

            if not patient_result:
                raise HTTPException(status_code=500, detail="Failed to create patient record")

            patient_id = patient_result[0]

        db.commit()  # Commit only if all insertions succeed

        ############################################################################################        
        print("===================================================================================")
        print("User_id :", user_id)
        # otp generare
        from ..models import generate_otp
        otp = generate_otp.generate_secure_otp(db, user_id)
        print(otp)


        # Create a 256-bit AES key from a password using SHA-256
        def get_aes_key_from_password(password: str) -> bytes:
            return hashlib.sha256(password.encode()).digest()

        # Encrypt an integer and return a Base64-safe string (no slashes or plus signs)
        def encrypt_int(value: int, password: str) -> str:
            key = get_aes_key_from_password(password)
            cipher = AES.new(key, AES.MODE_CBC)
            iv = cipher.iv  # Initialization vector
            data = str(value).encode()  # Convert integer to bytes
            encrypted = cipher.encrypt(pad(data, AES.block_size))  # Encrypt with padding
            
            # Encode with URL-safe base64 and remove trailing '='
            encrypted_b64 = base64.urlsafe_b64encode(iv + encrypted).decode().rstrip("=")
            return encrypted_b64


        encrypt_user_id = encrypt_int(user_id, os.getenv("USER_ID_PASSWORD"))
        
        ########################################################################################### 
        
        # Fetch complete user details after registration
        if user_type == "doctor":
            details_query = text("""
                SELECT 
                    ghp.id AS healthprof_id,
                    pp.name AS full_name,
                    pp.gender,
                    pp.mobile_number AS phone_number,
                    pp.code,
                    pp.ref,
                    pp.activation_date,
                    ghp.year_of_experience,
                    ru.login AS username,
                    ru.email
                FROM gnuhealth_healthprofessional ghp
                JOIN party_party pp ON ghp.name = pp.id
                JOIN res_user ru ON pp.internal_user = ru.id
                WHERE ghp.id = :health_prof_id
            """)
            user_details = db.execute(details_query, {"health_prof_id": health_prof_id}).fetchone()
            
            if user_details:
                return {
                    "success": True,
                    "message": f"{user_type.capitalize()} registered successfully",
                    "secret_user_id": encrypt_user_id,
                    "user_details": dict(user_details._mapping)
                }
            else:
                return {
                    "success": True,
                    "message": f"{user_type.capitalize()} registered successfully",
                    "user_id": user_id,
                    "secret_user_id": encrypt_user_id,
                    "party_id": party_id,
                    "code": generated_code,
                    "ref": reference_code,
                    "activation_date": datetime.now().strftime("%Y-%m-%d")
                }
        else:
            # For patient registration, return all details
            details_query = text("""
                SELECT 
                    gp.id AS patient_id,
                    pp.name AS full_name,
                    pp.gender,
                    pp.mobile_number AS phone_number,
                    pp.code,
                    pp.ref,
                    pp.activation_date,
                    ru.login AS username,
                    ru.email
                FROM gnuhealth_patient gp
                JOIN party_party pp ON gp.name = pp.id
                JOIN res_user ru ON pp.internal_user = ru.id
                WHERE gp.id = :patient_id
            """)
            user_details = db.execute(details_query, {"patient_id": patient_id}).fetchone()

            if user_details:
                return {
                    "success": True,
                    "message": f"{user_type.capitalize()} registered successfully",
                    "secret_user_id": encrypt_user_id,
                    "user_details": dict(user_details._mapping)
                }
            else:
                return {
                    "success": True,
                    "message": f"{user_type.capitalize()} registered successfully",
                    "user_id": user_id,
                    "secret_user_id": encrypt_user_id,
                    "party_id": party_id,
                    "patient_id": patient_id,
                    "code": generated_code,
                    "ref": reference_code,
                    "activation_date": datetime.now().strftime("%Y-%m-%d")
                }

    except Exception as e:
        db.rollback()
        
        if "duplicate key value violates unique constraint" in str(e):
            existing_user = db.execute(text("""
                SELECT id, otp_verified, otp_date FROM res_user WHERE login = :login
            """), {"login": user_name}).fetchone()
            if existing_user:
                user_id = existing_user.id
                otp_verified = existing_user.otp_verified
                otp_date = existing_user.otp_date
                current_time = db.execute(text("SELECT NOW() AT TIME ZONE 'Asia/Dhaka';")).fetchone()[0]
                print("================: ", current_time, "Otp date: ", otp_date)
                if otp_verified == "true":
                    raise HTTPException(status_code=400, detail="User already exists")
                
                elif (current_time - otp_date) > timedelta(minutes=5):
                    print("5 minutes conditions")
                    try:
                        user_status_info = db.execute(text("""
                                                           SELECT is_healthprof FROM party_party WHERE internal_user = :user_id
                                                           """), {"user_id": user_id}).fetchone()
                        if user_status_info[0] == True:
                            db.execute(text("""
                                DELETE FROM gnuhealth_healthprofessional
                                WHERE name IN (SELECT id FROM party_party WHERE internal_user = :user_id)
                            """), {"user_id": user_id})
                        else:
                            db.execute(text("""
                                DELETE FROM gnuhealth_patient
                                WHERE name IN (SELECT id FROM party_party WHERE internal_user = :user_id)
                            """), {"user_id": user_id})
                        db.execute(text("DELETE FROM party_party WHERE internal_user = :user_id"), {"user_id": user_id})
                        db.execute(text("DELETE FROM res_user WHERE id = :user_id"), {"user_id": user_id})
                        db.commit()
                        registration_info = register_user(user_type, data, db)
                        return registration_info
                        
                    except Exception as delete_error:
                        db.rollback()
                        raise HTTPException(status_code=500, detail=f"Cleanup failed: {delete_error}")
                else:
                    raise HTTPException(status_code=400, detail="User already exists and within 5-minute retry window")
        raise HTTPException(status_code=500, detail=f"Unexpected DB error: {str(e)}")
    # except Exception as e:
    #     if "duplicate key value violates unique constraint" in str(e):
    #         raise HTTPException(status_code=400, detail="User already exists")
    #     db.rollback()
    #     raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.put("/{user_type}/{id}/update")
def update_user_profile(
    user_type: str,
    id: int,
    data: dict,
    db: Session = Depends(get_db)
):
    """Update user profile dynamically for both doctors and patients"""

    if user_type not in ["doctor", "patient"]:
        raise HTTPException(status_code=400, detail="Invalid user type")

    # Common fields
    full_name = data.get("full_name")
    gender = data.get("gender")
    phone_number = data.get("phone_number")
    email = data.get("email")
    username = data.get("username")

    # Address info
    address_fields = {
        "address_city": data.get("address_city"),
        "address_municipality": data.get("address_municipality"),
        "address_street": data.get("address_street"),
        "address_street_bis": data.get("address_street_bis"),
        "address_street_number": data.get("address_street_number"),
        "address_zip": data.get("address_zip")
    }

    # Optional doctor-specific field
    year_of_experience = data.get("year_of_experience")

    try:
        if user_type == "doctor":
            # First get the party_id from gnuhealth_healthprofessional
            health_prof_query = text("""
                SELECT name FROM gnuhealth_healthprofessional WHERE id = :id
            """)
            health_prof = db.execute(health_prof_query, {"id": id}).fetchone()
            
            if not health_prof:
                raise HTTPException(status_code=404, detail="Doctor not found")
            
            party_id = health_prof.name

            # Get user_id from party_party
            party_query = text("""
                SELECT internal_user FROM party_party WHERE id = :party_id
            """)
            party = db.execute(party_query, {"party_id": party_id}).fetchone()
            
            if not party:
                raise HTTPException(status_code=404, detail="Party record not found")
            
            user_id = party.internal_user

        else:  # patient
            # Get party_id from gnuhealth_patient
            patient_query = text("""
                SELECT name FROM gnuhealth_patient WHERE id = :id
            """)
            patient = db.execute(patient_query, {"id": id}).fetchone()
            
            if not patient:
                raise HTTPException(status_code=404, detail="Patient not found")
            
            party_id = patient.name

            # Get user_id from party_party
            party_query = text("""
                SELECT internal_user FROM party_party WHERE id = :party_id
            """)
            party = db.execute(party_query, {"party_id": party_id}).fetchone()
            
            if not party:
                raise HTTPException(status_code=404, detail="Party record not found")
            
            user_id = party.internal_user

        # 1. Update party_party
        db.execute(text("""
            UPDATE party_party
            SET name = COALESCE(:full_name, name),
                gender = COALESCE(:gender, gender),
                mobile_number = COALESCE(:phone_number, mobile_number),
                write_date = :now,
                write_uid = 1
            WHERE id = :party_id
        """), {
            "full_name": full_name,
            "gender": gender,
            "phone_number": phone_number,
            "now": datetime.now(),
            "party_id": party_id
        })

        # 2. Update res_user
        if user_id:
            db.execute(text("""
                UPDATE res_user
                SET login = COALESCE(:username, login),
                    email = COALESCE(:email, email)
                WHERE id = :user_id
            """), {
                "username": username,
                "email": email,
                "user_id": user_id
            })

        # 3. Update gnuhealth_healthprofessional if doctor
        if user_type == "doctor" and year_of_experience is not None:
            db.execute(text("""
                UPDATE gnuhealth_healthprofessional
                SET year_of_experience = :year_of_experience
                WHERE id = :id
            """), {
                "year_of_experience": year_of_experience,
                "id": id
            })

        # 4. Handle address information
        du_query = text("""
            SELECT du FROM party_party WHERE id = :party_id
        """)
        du_result = db.execute(du_query, {"party_id": party_id}).fetchone()
        
        # Check if any address fields are provided
        has_address_fields = any(value is not None for value in address_fields.values())
        
        if has_address_fields:
            if du_result and du_result.du:
                # Update existing address
                db.execute(text("""
                    UPDATE gnuhealth_du
                    SET address_city = COALESCE(:address_city, address_city),
                        address_municipality = COALESCE(:address_municipality, address_municipality),
                        address_street = COALESCE(:address_street, address_street),
                        address_street_bis = COALESCE(:address_street_bis, address_street_bis),
                        address_street_number = COALESCE(:address_street_number, address_street_number),
                        address_zip = COALESCE(:address_zip, address_zip)
                    WHERE id = :du_id
                """), {**address_fields, "du_id": du_result.du})
            else:
                # Create new address record
                du_insert = text("""
                    INSERT INTO gnuhealth_du (
                        name, address_city, address_municipality, address_street,
                        address_street_bis, address_street_number, address_zip,
                        create_date, create_uid, write_date, write_uid
                    ) VALUES (
                        :name, :address_city, :address_municipality, :address_street,
                        :address_street_bis, :address_street_number, :address_zip,
                        :create_date, :create_uid, :write_date, :write_uid
                    ) RETURNING id
                """)
                du_id = db.execute(du_insert, {
                    "name": f"Address for {full_name}",  # Using the doctor's name for the address record
                    **address_fields,
                    "create_date": datetime.now(),
                    "create_uid": 1,
                    "write_date": datetime.now(),
                    "write_uid": 1
                }).fetchone()[0]
                
                # Update party_party with new du_id
                db.execute(text("""
                    UPDATE party_party
                    SET du = :du_id
                    WHERE id = :party_id
                """), {"du_id": du_id, "party_id": party_id})

        db.commit()

        # Fetch updated user details
        if user_type == "doctor":
            details_query = text("""
                SELECT 
                    ghp.id AS healthprof_id,
                    pp.name AS full_name,
                    pp.gender,
                    pp.mobile_number AS phone_number,
                    pp.code,
                    pp.ref,
                    pp.activation_date,
                    ghp.year_of_experience,
                    ru.login AS username,
                    ru.email,
                    gdu.address_city,
                    gdu.address_municipality,
                    gdu.address_street,
                    gdu.address_street_bis,
                    gdu.address_street_number,
                    gdu.address_zip
                FROM gnuhealth_healthprofessional ghp
                JOIN party_party pp ON ghp.name = pp.id
                JOIN res_user ru ON pp.internal_user = ru.id
                LEFT JOIN gnuhealth_du gdu ON pp.du = gdu.id
                WHERE ghp.id = :id
            """)
        else:  # patient
            details_query = text("""
                SELECT 
                    gp.id AS patient_id,
                    pp.name AS full_name,
                    pp.gender,
                    pp.mobile_number AS phone_number,
                    pp.code,
                    pp.ref,
                    pp.activation_date,
                    ru.login AS username,
                    ru.email,
                    gdu.address_city,
                    gdu.address_municipality,
                    gdu.address_street,
                    gdu.address_street_bis,
                    gdu.address_street_number,
                    gdu.address_zip
                FROM gnuhealth_patient gp
                JOIN party_party pp ON gp.name = pp.id
                JOIN res_user ru ON pp.internal_user = ru.id
                LEFT JOIN gnuhealth_du gdu ON pp.du = gdu.id
                WHERE gp.id = :id
            """)

        updated_details = db.execute(details_query, {"id": id}).fetchone()
        
        if updated_details:
            return {
                "success": True,
                "message": f"{user_type.capitalize()} profile updated successfully",
                "user_details": dict(updated_details._mapping)
            }
        else:
            return {
                "success": True,
                "message": f"{user_type.capitalize()} profile updated successfully",
                "warning": "Could not fetch updated details"
            }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")
