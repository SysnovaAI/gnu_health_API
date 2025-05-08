from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi.responses import JSONResponse
from ..models.base import get_db
from .appointments import get_current_user
from pydantic import BaseModel
import uuid
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.put("/profile-update")
def update_user_profile(
    data: dict,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update user profile dynamically for both doctors and patients"""

    user_id = user.get("id")
    
    # user_id = 88
    user_type = text("""
                SELECT 
                    pp.id,
                    CASE 
                        WHEN pp.is_healthprof THEN gh.id 
                        ELSE NULL 
                    END AS healthprof_id,
                    CASE 
                        WHEN pp.is_patient THEN gp.id 
                        ELSE NULL 
                    END AS patient_id,
                    pp.is_healthprof, 
                    pp.is_patient
                    FROM res_user ru
                    JOIN party_party pp ON pp.internal_user = ru.id
                    LEFT JOIN gnuhealth_healthprofessional gh ON pp.id = gh.name
                    LEFT JOIN gnuhealth_patient gp ON pp.id = gp.name
                    WHERE ru.id = :user;

            """)
    user_types = db.execute(user_type, {"user": user_id}).fetchone()
    is_healthprofs, is_patients = user_types.is_healthprof, user_types.is_patient

    if not (is_healthprofs or is_patients):
        raise HTTPException(status_code=400, detail="You have no access for update the profile only doctor and patient have access")
    
    party_id = user_types.id

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

    # # Optional doctor-specific field
    year_of_experience = data.get("year_of_experience")

    try:
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
                    email = COALESCE(:email, email),
                    name = COALESCE(:full_name, name)
                WHERE id = :user_id
            """), {
                "username": username,
                "email": email,
                "full_name": full_name,
                "user_id": user_id
            })

        # 3. Update gnuhealth_healthprofessional if doctor
        if is_healthprofs == True and year_of_experience is not None:

            db.execute(text("""
                UPDATE gnuhealth_healthprofessional
                SET year_of_experience = :year_of_experience
                WHERE id = :id
            """), {
                "year_of_experience": year_of_experience,
                "id": user_types.healthprof_id
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
        if is_healthprofs == True:
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
            result = db.execute(details_query, {"id": user_types.healthprof_id}).fetchone()
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

            result = db.execute(details_query, {"id": user_types.patient_id}).fetchone()
        

        role = "Doctor" if is_healthprofs else "Patient"

        return {
            "success": True,
            "message": f"{role} profile updated successfully",
            "user_details": dict(result._mapping) if result else {}
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=403, detail=f"Update failed: Provided information already exist")
