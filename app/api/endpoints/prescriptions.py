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

class AppointmentDetailsRequest(BaseModel):
    appointment_id: int

# Add doctor authentication check
async def verify_doctor(user: dict = Depends(get_current_user)):
    if not user or user.get("role") != "doctor":
        raise HTTPException(
            status_code=403,
            detail="Only doctors can access this endpoint"
        )
    return user

async def cleanup_default_medicines(db: Session):
    """Clean up default medicines and their associated party entries."""
    try:
        # First find all default medicines
        find_default_meds_query = text("""
            SELECT id, name 
            FROM gnuhealth_medicament 
            WHERE active_component = 'Default Medicine'
        """)
        default_meds = db.execute(find_default_meds_query).fetchall()
        
        if not default_meds:
            logger.info("No default medicines found to clean up")
            return
        
        logger.info(f"Found {len(default_meds)} default medicines to clean up")
        
        # Delete prescription lines referencing these medicines
        delete_prescription_lines_query = text("""
            DELETE FROM gnuhealth_prescription_line
            WHERE medicament IN :med_ids
        """)
        db.execute(delete_prescription_lines_query, {"med_ids": tuple(med.id for med in default_meds)})
        
        # Delete the medicines
        delete_medicines_query = text("""
            DELETE FROM gnuhealth_medicament
            WHERE id IN :med_ids
        """)
        db.execute(delete_medicines_query, {"med_ids": tuple(med.id for med in default_meds)})
        
        # Delete associated party entries
        delete_party_query = text("""
            DELETE FROM party_party
            WHERE id IN :party_ids
        """)
        db.execute(delete_party_query, {"party_ids": tuple(med.name for med in default_meds)})
        
        db.commit()
        logger.info("Successfully cleaned up default medicines")
        
    except Exception as e:
        logger.error(f"Error cleaning up default medicines: {str(e)}")
        db.rollback()
        raise

@router.post("/prescription-header")
async def get_appointment_details(
    request: AppointmentDetailsRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(verify_doctor)
):
    try:
        # Clean up any existing default medicines
        await cleanup_default_medicines(db)
        
        logger.debug(f"Starting prescription-header for appointment_id: {request.appointment_id}")
        
        # First get the appointment details including status
        appointment_query = text("""
            SELECT 
                ga.id,
                ga.patient,
                ga.healthprof,
                ga.state
            FROM gnuhealth_appointment ga
            WHERE ga.id = :appointment_id
        """)
        
        appointment = db.execute(appointment_query, {"appointment_id": request.appointment_id}).fetchone()
        
        if not appointment:
            logger.error(f"Appointment not found: {request.appointment_id}")
            return JSONResponse(
                content={"message": "Appointment not found"},
                status_code=404
            )

        # Add detailed logging for debugging
        logger.debug(f"Logged in user ID: {user.get('id')}")
        logger.debug(f"Appointment healthprof ID: {appointment.healthprof}")

        # Get the internal_user ID for the healthprof
        healthprof_query = text("""
            SELECT pp.internal_user
            FROM gnuhealth_healthprofessional ghp
            JOIN party_party pp ON ghp.name = pp.id
            WHERE ghp.id = :healthprof_id
        """)
        
        healthprof_internal_user = db.execute(
            healthprof_query, 
            {"healthprof_id": appointment.healthprof}
        ).fetchone()

        if not healthprof_internal_user:
            logger.error(f"Health professional details not found for ID: {appointment.healthprof}")
            raise HTTPException(
                status_code=404,
                detail="Health professional details not found"
            )

        logger.debug(f"Health professional internal user ID: {healthprof_internal_user.internal_user}")

        # Verify if the logged-in doctor is the one assigned to this appointment
        if healthprof_internal_user.internal_user != user.get("id"):
            logger.error(f"Authorization failed - Doctor ID mismatch. Expected internal_user: {healthprof_internal_user.internal_user}, Got: {user.get('id')}")
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to access this appointment"
            )

        # Check if appointment is booked
        if appointment.state != 'confirmed':
            logger.error(f"Appointment is not in booked state. Current state: {appointment.state}")
            return JSONResponse(
                content={"message": "Appointment has not been booked"},
                status_code=400
            )

        logger.debug(f"Found appointment: {appointment.id}")

        # Generate prescription ID
        current_year = datetime.now().year
        prescription_id = f"PRES {current_year}/{request.appointment_id}"
        logger.debug(f"Generated prescription_id: {prescription_id}")

        try:
            # First check if default medicine exists
            check_medicine_query = text("""
                SELECT id FROM gnuhealth_medicament 
                WHERE active_component = 'Default Medicine'
            """)
            medicine_result = db.execute(check_medicine_query).fetchone()

            if not medicine_result:
                # Generate a unique code for the party
                party_code = f"MED_{str(uuid.uuid4())[:8]}"
                
                # Create party entry for the medicine
                create_party_query = text("""
                    INSERT INTO party_party (name, code)
                    VALUES (:name, :code)
                    RETURNING id
                """)
                party_result = db.execute(
                    create_party_query,
                    {
                        "name": "Default Medicine",
                        "code": party_code
                    }
                ).fetchone()
                
                if not party_result:
                    logger.error("Failed to create party entry")
                    return JSONResponse(
                        content={"message": "Failed to create party entry"},
                        status_code=500
                    )

                # Create medicine entry
                create_medicine_query = text("""
                    INSERT INTO gnuhealth_medicament (name, active_component)
                    VALUES (:party_id, 'Default Medicine')
                    RETURNING id
                """)
                medicine_result = db.execute(
                    create_medicine_query,
                    {"party_id": party_result.id}
                ).fetchone()

                if not medicine_result:
                    logger.error("Failed to create medicine entry")
                    return JSONResponse(
                        content={"message": "Failed to create medicine entry"},
                        status_code=500
                    )

            # Create prescription order and line in a single transaction
            create_query = text("""
                WITH new_order AS (
                    INSERT INTO gnuhealth_prescription_order (
                        appointment_id, 
                        prescription_id,
                        patient,
                        healthprof,
                        create_date,
                        create_uid,
                        prescription_date,
                        user_id,
                        write_date,
                        write_uid
                    )
                    VALUES (
                        :appointment_id, 
                        :prescription_id,
                        :patient,
                        :healthprof,
                        now(),
                        :internal_user,
                        now(),
                        :internal_user,
                        now(),
                        :internal_user
                    )
                    RETURNING id
                )
                INSERT INTO gnuhealth_prescription_line (
                    name,
                    create_date,
                    create_uid,
                    start_treatment,
                    review,
                    write_date,
                    write_uid,
                    medicament
                )
                SELECT 
                    id,
                    now(),
                    :internal_user,
                    now(),
                    now(),
                    now(),
                    :internal_user,
                    :medicament_id
                FROM new_order
                RETURNING id
            """)
            
            logger.debug("Executing create query with params:")
            logger.debug(f"appointment_id: {request.appointment_id}")
            logger.debug(f"prescription_id: {prescription_id}")
            logger.debug(f"patient: {appointment.patient}")
            logger.debug(f"healthprof: {appointment.healthprof}")
            logger.debug(f"internal_user: {healthprof_internal_user.internal_user}")
            logger.debug(f"medicament_id: {medicine_result.id}")
            
            result = db.execute(
                create_query,
                {
                    "appointment_id": request.appointment_id,
                    "prescription_id": prescription_id,
                    "patient": appointment.patient,
                    "healthprof": appointment.healthprof,
                    "internal_user": healthprof_internal_user.internal_user,
                    "medicament_id": medicine_result.id
                }
            ).fetchone()
            
            if result:
                logger.debug(f"Successfully created prescription with ID: {result.id}")
                db.commit()
            else:
                logger.error("Failed to create prescription - no result returned")
                db.rollback()
                return JSONResponse(
                    content={"message": "Failed to create prescription order and line"},
                    status_code=500
                )

        except Exception as e:
            logger.error(f"Database error: {str(e)}")
            db.rollback()
            return JSONResponse(
                content={"message": f"Database error: {str(e)}"},
                status_code=500
            )

        # Get diagnosis information from patient evaluation
        diagnosis_query = text("""
            SELECT 
                id,
                chief_complaint,
                systolic,
                glycemia,
                weight,
                height
            FROM gnuhealth_patient_evaluation
            WHERE appointment = :appointment_id
        """)
        
        diagnosis = db.execute(diagnosis_query, {"appointment_id": request.appointment_id}).fetchone()
        
        # If no diagnosis exists, create a blank row
        if not diagnosis:
            create_diagnosis_query = text("""
                INSERT INTO gnuhealth_patient_evaluation (
                    appointment,
                    chief_complaint,
                    systolic,
                    glycemia,
                    weight,
                    height,
                    discharge_reason,
                    evaluation_start
                )
                VALUES (
                    :appointment_id,
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    'routine',  -- Default value for discharge_reason
                    CURRENT_TIMESTAMP  -- Current timestamp for evaluation_start
                )
                RETURNING id, chief_complaint, systolic, glycemia, weight, height
            """)
            diagnosis = db.execute(
                create_diagnosis_query,
                {"appointment_id": request.appointment_id}
            ).fetchone()
            db.commit()

        # Get patient details with all information from gnuhealth_patient
        patient_query = text("""
            SELECT 
                gp.*,
                pp.name as patient_name,
                pp.gender,
                pp.mobile_number,
                pp.internal_user
            FROM gnuhealth_patient gp
            JOIN party_party pp ON gp.name = pp.id
            WHERE gp.id = :patient_id
        """)
        
        patient = db.execute(patient_query, {"patient_id": appointment.patient}).fetchone()
        
        if not patient:
            return JSONResponse(
                content={"message": "Patient details not found"},
                status_code=404
            )
            
        # Get patient email
        patient_user_query = text("""
            SELECT email
            FROM res_user
            WHERE id = :internal_user
        """)
        
        patient_user = db.execute(patient_user_query, {"internal_user": patient.internal_user}).fetchone()
        
        # Get doctor details
        doctor_query = text("""
            SELECT 
                pp.name as doctor_name,
                ghp.main_specialty,
                pp.mobile_number,
                ru.email
            FROM gnuhealth_healthprofessional ghp
            JOIN party_party pp ON ghp.name = pp.id
            JOIN res_user ru ON pp.internal_user = ru.id
            WHERE ghp.id = :healthprof_id
        """)
        
        doctor = db.execute(doctor_query, {"healthprof_id": appointment.healthprof}).fetchone()
        
        if not doctor:
            return JSONResponse(
                content={"message": "Doctor details not found"},
                status_code=404
            )

        # Build patient details dynamically based on available fields
        patient_details = {
            "name": patient.patient_name,
            "gender": patient.gender,
            "mobile_number": patient.mobile_number,
            "email": patient_user.email if patient_user else None
        }

        # Add additional fields if they exist
        if hasattr(patient, 'birth_date') and patient.birth_date:
            patient_details["birth_date"] = patient.birth_date.strftime("%Y-%m-%d")
        if hasattr(patient, 'blood_type') and patient.blood_type:
            patient_details["blood_type"] = patient.blood_type
        if hasattr(patient, 'rh') and patient.rh:
            patient_details["rh"] = patient.rh
        if hasattr(patient, 'marital_status') and patient.marital_status:
            patient_details["marital_status"] = patient.marital_status
        if hasattr(patient, 'occupation') and patient.occupation:
            patient_details["occupation"] = patient.occupation
        if hasattr(patient, 'education') and patient.education:
            patient_details["education"] = patient.education
        if hasattr(patient, 'ethnicity') and patient.ethnicity:
            patient_details["ethnicity"] = patient.ethnicity
        if hasattr(patient, 'identification_code') and patient.identification_code:
            patient_details["identification_code"] = patient.identification_code
        if hasattr(patient, 'passport_number') and patient.passport_number:
            patient_details["passport_number"] = patient.passport_number

        # Build insurance details if they exist
        insurance_details = {}
        if hasattr(patient, 'insurance_company') and patient.insurance_company:
            insurance_details["company"] = patient.insurance_company
        if hasattr(patient, 'insurance_number') and patient.insurance_number:
            insurance_details["number"] = patient.insurance_number
        if hasattr(patient, 'insurance_type') and patient.insurance_type:
            insurance_details["type"] = patient.insurance_type
        if hasattr(patient, 'insurance_plan') and patient.insurance_plan:
            insurance_details["plan"] = patient.insurance_plan
        if hasattr(patient, 'insurance_network') and patient.insurance_network:
            insurance_details["network"] = patient.insurance_network
        if hasattr(patient, 'insurance_coverage') and patient.insurance_coverage:
            insurance_details["coverage"] = patient.insurance_coverage
        if hasattr(patient, 'insurance_validity') and patient.insurance_validity:
            insurance_details["validity"] = patient.insurance_validity
        if hasattr(patient, 'insurance_notes') and patient.insurance_notes:
            insurance_details["notes"] = patient.insurance_notes

        if insurance_details:
            patient_details["insurance"] = insurance_details

        # Build diagnosis details if they exist
        diagnosis_details = {}
        if diagnosis:
            if hasattr(diagnosis, 'chief_complaint') and diagnosis.chief_complaint:
                diagnosis_details["complain"] = diagnosis.chief_complaint
            if hasattr(diagnosis, 'systolic') and diagnosis.systolic:
                diagnosis_details["blood_pressure"] = diagnosis.systolic
            if hasattr(diagnosis, 'glycemia') and diagnosis.glycemia:
                diagnosis_details["sugar_level"] = diagnosis.glycemia
            if hasattr(diagnosis, 'weight') and diagnosis.weight:
                diagnosis_details["weight"] = diagnosis.weight
            if hasattr(diagnosis, 'height') and diagnosis.height:
                diagnosis_details["height"] = diagnosis.height
            
        # Build medical history from gnuhealth_patient
        medical_history = {}
        if hasattr(patient, 'id'): medical_history["id"] = patient.id
        if hasattr(patient, 'active'): medical_history["active"] = patient.active
        if hasattr(patient, 'biological_sex'): medical_history["biological_sex"] = patient.biological_sex
        if hasattr(patient, 'blood_type'): medical_history["blood_type"] = patient.blood_type
        if hasattr(patient, 'create_date'): medical_history["create_date"] = patient.create_date.strftime("%Y-%m-%d %H:%M:%S") if patient.create_date else None
        if hasattr(patient, 'create_uid'): medical_history["create_uid"] = patient.create_uid
        if hasattr(patient, 'crit_allergic'): medical_history["crit_allergic"] = patient.crit_allergic
        if hasattr(patient, 'crit_cancer'): medical_history["crit_cancer"] = patient.crit_cancer
        if hasattr(patient, 'crit_cardio'): medical_history["crit_cardio"] = patient.crit_cardio
        if hasattr(patient, 'crit_cognitive'): medical_history["crit_cognitive"] = patient.crit_cognitive
        if hasattr(patient, 'crit_dbt'): medical_history["crit_dbt"] = patient.crit_dbt
        if hasattr(patient, 'crit_hbp'): medical_history["crit_hbp"] = patient.crit_hbp
        if hasattr(patient, 'crit_immuno'): medical_history["crit_immuno"] = patient.crit_immuno
        if hasattr(patient, 'crit_nutrition'): medical_history["crit_nutrition"] = patient.crit_nutrition
        if hasattr(patient, 'crit_social'): medical_history["crit_social"] = patient.crit_social
        if hasattr(patient, 'critical_info'): medical_history["critical_info"] = patient.critical_info
        if hasattr(patient, 'current_address'): medical_history["current_address"] = patient.current_address
        if hasattr(patient, 'current_insurance'): medical_history["current_insurance"] = patient.current_insurance
        if hasattr(patient, 'family'): medical_history["family"] = patient.family
        if hasattr(patient, 'general_info'): medical_history["general_info"] = patient.general_info
        if hasattr(patient, 'hb'): medical_history["hb"] = patient.hb
        if hasattr(patient, 'name'): medical_history["name"] = patient.name
        if hasattr(patient, 'primary_care_doctor'): medical_history["primary_care_doctor"] = patient.primary_care_doctor
        if hasattr(patient, 'rh'): medical_history["rh"] = patient.rh
        if hasattr(patient, 'write_date'): medical_history["write_date"] = patient.write_date.strftime("%Y-%m-%d %H:%M:%S") if patient.write_date else None
        if hasattr(patient, 'write_uid'): medical_history["write_uid"] = patient.write_uid
        if hasattr(patient, 'dental_schema'): medical_history["dental_schema"] = patient.dental_schema
        if hasattr(patient, 'dental_schema_primary'): medical_history["dental_schema_primary"] = patient.dental_schema_primary
        if hasattr(patient, 'use_primary_schema'): medical_history["use_primary_schema"] = patient.use_primary_schema
        if hasattr(patient, 'breast_self_examination'): medical_history["breast_self_examination"] = patient.breast_self_examination
        if hasattr(patient, 'colposcopy'): medical_history["colposcopy"] = patient.colposcopy
        if hasattr(patient, 'colposcopy_last'): medical_history["colposcopy_last"] = patient.colposcopy_last
        if hasattr(patient, 'fertile'): medical_history["fertile"] = patient.fertile
        if hasattr(patient, 'full_term'): medical_history["full_term"] = patient.full_term
        if hasattr(patient, 'mammography'): medical_history["mammography"] = patient.mammography
        if hasattr(patient, 'mammography_last'): medical_history["mammography_last"] = patient.mammography_last
        if hasattr(patient, 'menarche'): medical_history["menarche"] = patient.menarche
        if hasattr(patient, 'menopausal'): medical_history["menopausal"] = patient.menopausal
        if hasattr(patient, 'menopause'): medical_history["menopause"] = patient.menopause
        if hasattr(patient, 'pap_test'): medical_history["pap_test"] = patient.pap_test
        if hasattr(patient, 'pap_test_last'): medical_history["pap_test_last"] = patient.pap_test_last
        if hasattr(patient, 'age_quit_drinking'): medical_history["age_quit_drinking"] = patient.age_quit_drinking
        if hasattr(patient, 'age_quit_drugs'): medical_history["age_quit_drugs"] = patient.age_quit_drugs
        if hasattr(patient, 'age_quit_smoking'): medical_history["age_quit_smoking"] = patient.age_quit_smoking
        if hasattr(patient, 'age_start_drinking'): medical_history["age_start_drinking"] = patient.age_start_drinking
        if hasattr(patient, 'age_start_drugs'): medical_history["age_start_drugs"] = patient.age_start_drugs
        if hasattr(patient, 'age_start_smoking'): medical_history["age_start_smoking"] = patient.age_start_smoking
        if hasattr(patient, 'alcohol'): medical_history["alcohol"] = patient.alcohol
        if hasattr(patient, 'alcohol_beer_number'): medical_history["alcohol_beer_number"] = patient.alcohol_beer_number
        if hasattr(patient, 'alcohol_liquor_number'): medical_history["alcohol_liquor_number"] = patient.alcohol_liquor_number
        if hasattr(patient, 'alcohol_wine_number'): medical_history["alcohol_wine_number"] = patient.alcohol_wine_number
        if hasattr(patient, 'anticonceptive'): medical_history["anticonceptive"] = patient.anticonceptive
        if hasattr(patient, 'car_child_safety'): medical_history["car_child_safety"] = patient.car_child_safety
        if hasattr(patient, 'car_revision'): medical_history["car_revision"] = patient.car_revision
        if hasattr(patient, 'car_seat_belt'): medical_history["car_seat_belt"] = patient.car_seat_belt
        if hasattr(patient, 'coffee'): medical_history["coffee"] = patient.coffee
        if hasattr(patient, 'coffee_cups'): medical_history["coffee_cups"] = patient.coffee_cups
        if hasattr(patient, 'diet'): medical_history["diet"] = patient.diet
        if hasattr(patient, 'diet_belief'): medical_history["diet_belief"] = patient.diet_belief
        if hasattr(patient, 'diet_info'): medical_history["diet_info"] = patient.diet_info
        if hasattr(patient, 'drug_iv'): medical_history["drug_iv"] = patient.drug_iv
        if hasattr(patient, 'drug_usage'): medical_history["drug_usage"] = patient.drug_usage
        if hasattr(patient, 'eats_alone'): medical_history["eats_alone"] = patient.eats_alone
        if hasattr(patient, 'ex_alcoholic'): medical_history["ex_alcoholic"] = patient.ex_alcoholic
        if hasattr(patient, 'ex_drug_addict'): medical_history["ex_drug_addict"] = patient.ex_drug_addict
        if hasattr(patient, 'ex_smoker'): medical_history["ex_smoker"] = patient.ex_smoker
        if hasattr(patient, 'exercise'): medical_history["exercise"] = patient.exercise
        if hasattr(patient, 'exercise_minutes_day'): medical_history["exercise_minutes_day"] = patient.exercise_minutes_day
        if hasattr(patient, 'first_sexual_encounter'): medical_history["first_sexual_encounter"] = patient.first_sexual_encounter
        if hasattr(patient, 'helmet'): medical_history["helmet"] = patient.helmet
        if hasattr(patient, 'home_safety'): medical_history["home_safety"] = patient.home_safety
        if hasattr(patient, 'lifestyle_info'): medical_history["lifestyle_info"] = patient.lifestyle_info
        if hasattr(patient, 'motorcycle_rider'): medical_history["motorcycle_rider"] = patient.motorcycle_rider
        if hasattr(patient, 'number_of_meals'): medical_history["number_of_meals"] = patient.number_of_meals
        if hasattr(patient, 'prostitute'): medical_history["prostitute"] = patient.prostitute
        if hasattr(patient, 'salt'): medical_history["salt"] = patient.salt
        if hasattr(patient, 'second_hand_smoker'): medical_history["second_hand_smoker"] = patient.second_hand_smoker
        if hasattr(patient, 'sex_anal'): medical_history["sex_anal"] = patient.sex_anal
        if hasattr(patient, 'sex_oral'): medical_history["sex_oral"] = patient.sex_oral
        if hasattr(patient, 'sex_with_prostitutes'): medical_history["sex_with_prostitutes"] = patient.sex_with_prostitutes
        if hasattr(patient, 'sexual_partners'): medical_history["sexual_partners"] = patient.sexual_partners
        if hasattr(patient, 'sexual_partners_number'): medical_history["sexual_partners_number"] = patient.sexual_partners_number
        if hasattr(patient, 'sexual_practices'): medical_history["sexual_practices"] = patient.sexual_practices
        if hasattr(patient, 'sexual_preferences'): medical_history["sexual_preferences"] = patient.sexual_preferences
        if hasattr(patient, 'sexuality_info'): medical_history["sexuality_info"] = patient.sexuality_info
        if hasattr(patient, 'sleep_during_daytime'): medical_history["sleep_during_daytime"] = patient.sleep_during_daytime
        if hasattr(patient, 'sleep_hours'): medical_history["sleep_hours"] = patient.sleep_hours
        if hasattr(patient, 'smoking'): medical_history["smoking"] = patient.smoking
        if hasattr(patient, 'smoking_number'): medical_history["smoking_number"] = patient.smoking_number
        if hasattr(patient, 'soft_drinks'): medical_history["soft_drinks"] = patient.soft_drinks
        if hasattr(patient, 'traffic_laws'): medical_history["traffic_laws"] = patient.traffic_laws
        if hasattr(patient, 'vegetarian_type'): medical_history["vegetarian_type"] = patient.vegetarian_type
        if hasattr(patient, 'domestic_violence'): medical_history["domestic_violence"] = patient.domestic_violence
        if hasattr(patient, 'drug_addiction'): medical_history["drug_addiction"] = patient.drug_addiction
        if hasattr(patient, 'hostile_area'): medical_history["hostile_area"] = patient.hostile_area
        if hasattr(patient, 'hours_outside'): medical_history["hours_outside"] = patient.hours_outside
        if hasattr(patient, 'prison_current'): medical_history["prison_current"] = patient.prison_current
        if hasattr(patient, 'prison_past'): medical_history["prison_past"] = patient.prison_past
        if hasattr(patient, 'relative_in_prison'): medical_history["relative_in_prison"] = patient.relative_in_prison
        if hasattr(patient, 'school_withdrawal'): medical_history["school_withdrawal"] = patient.school_withdrawal
        if hasattr(patient, 'ses_notes'): medical_history["ses_notes"] = patient.ses_notes
        if hasattr(patient, 'sexual_abuse'): medical_history["sexual_abuse"] = patient.sexual_abuse
        if hasattr(patient, 'single_parent'): medical_history["single_parent"] = patient.single_parent
        if hasattr(patient, 'teenage_pregnancy'): medical_history["teenage_pregnancy"] = patient.teenage_pregnancy
        if hasattr(patient, 'working_children'): medical_history["working_children"] = patient.working_children
        if hasattr(patient, 'works_at_home'): medical_history["works_at_home"] = patient.works_at_home
        if hasattr(patient, 'amputee'): medical_history["amputee"] = patient.amputee
        if hasattr(patient, 'amputee_since'): medical_history["amputee_since"] = patient.amputee_since
        if hasattr(patient, 'disability'): medical_history["disability"] = patient.disability
        if hasattr(patient, 'uxo'): medical_history["uxo"] = patient.uxo

        # Get medical tests and medicines
        med_tests = {}
        medicines = {}
        
        # Get all tests and medicines in a single query using joins
        prescription_query = text("""
            WITH tests AS (
                SELECT DISTINCT
                    gplt.id as test,
                    gltt.name AS test_name
                FROM gnuhealth_prescription_order gpo
                LEFT JOIN gnuhealth_patient_lab_test gplt ON gpo.id = gplt.prescription
                LEFT JOIN gnuhealth_lab_test_type gltt ON gplt.name = gltt.id
                WHERE gpo.appointment_id = :appointment_id
            ),
            medicines AS (
                SELECT DISTINCT
                    gpl.medicament,
                    gm.active_component
                FROM gnuhealth_prescription_order gpo
                LEFT JOIN gnuhealth_prescription_line gpl ON gpo.id = gpl.name
                LEFT JOIN gnuhealth_medicament gm ON gm.id = gpl.medicament
                WHERE gpo.appointment_id = :appointment_id
                AND gm.active_component != 'Default Medicine'
            )
            SELECT 
                t.test,
                t.test_name,
                m.medicament,
                m.active_component
            FROM tests t
            FULL OUTER JOIN medicines m ON 1=1
            WHERE t.test IS NOT NULL OR m.medicament IS NOT NULL
        """)
        
        prescriptions = db.execute(prescription_query, {"appointment_id": request.appointment_id}).fetchall()
        
        # Add tests and medicines with sequential keys
        test_idx = 1
        med_idx = 1
        
        # Track unique medicines to avoid duplicates
        unique_medicines = set()
        
        for prescription in prescriptions:
            # Add test if it exists and not already added
            if prescription.test_name and prescription.test_name not in med_tests.values():
                test_key = f"test_name_{test_idx}"
                med_tests[test_key] = prescription.test_name
                test_idx += 1
                
            # Add medicine if it exists and not already added
            if prescription.active_component and prescription.active_component not in unique_medicines:
                med_key = f"medicine_{med_idx}"
                medicines[med_key] = prescription.active_component
                unique_medicines.add(prescription.active_component)
                med_idx += 1

        # Get remarks from gnuhealth_prescription_order
        remarks = {}
        remarks_query = text("""
            SELECT notes
            FROM gnuhealth_prescription_order
            WHERE appointment_id = :appointment_id
        """)
        
        prescription_order = db.execute(remarks_query, {"appointment_id": request.appointment_id}).fetchone()
        
        if prescription_order and prescription_order.notes:
            remarks["text"] = prescription_order.notes

        # Format the response
        response = {
            "appointment_id": appointment.id,
            "patient_details": patient_details,
            "doctor_details": {
                "name": doctor.doctor_name,
                "specialization": doctor.main_specialty,
                "mobile_number": doctor.mobile_number,
                "email": doctor.email
            },
            "Diagnosis": diagnosis_details if diagnosis_details else None,
            "medical_history": medical_history,
            "med_tests": med_tests if med_tests else None,
            "medicine": medicines if medicines else None,
            "remarks": remarks if remarks else None
        }
        
        return JSONResponse(
            content=response,
            status_code=200
        )
        
    except Exception as e:
        return JSONResponse(
            content={"message": f"Error occurred: {str(e)}"},
            status_code=500
        )

@router.post("/cleanup-default-medicines")
async def cleanup_medicines(
    db: Session = Depends(get_db),
    user: dict = Depends(verify_doctor)
):
    """Endpoint to manually trigger cleanup of default medicines."""
    try:
        await cleanup_default_medicines(db)
        return JSONResponse(
            content={"message": "Default medicines cleaned up successfully"},
            status_code=200
        )
    except Exception as e:
        return JSONResponse(
            content={"message": f"Error cleaning up default medicines: {str(e)}"},
            status_code=500
        ) 