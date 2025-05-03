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

# Add patient authentication check
async def verify_patient(user: dict = Depends(get_current_user)):
    if not user or user.get("role") != "patient":
        raise HTTPException(
            status_code=403,
            detail="Only patients can access this endpoint"
        )
    return user

@router.post("/patient-prescription")
async def get_patient_prescription(
    request: AppointmentDetailsRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(verify_patient)
):
    try:
        logger.debug(f"Starting patient-prescription for appointment_id: {request.appointment_id}")
        
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
        logger.debug(f"Appointment patient ID: {appointment.patient}")

        # Get the internal_user ID for the patient
        patient_query = text("""
            SELECT pp.internal_user
            FROM gnuhealth_patient gp
            JOIN party_party pp ON gp.name = pp.id
            WHERE gp.id = :patient_id
        """)
        
        patient_internal_user = db.execute(
            patient_query, 
            {"patient_id": appointment.patient}
        ).fetchone()

        if not patient_internal_user:
            logger.error(f"Patient details not found for ID: {appointment.patient}")
            raise HTTPException(
                status_code=404,
                detail="Patient details not found"
            )

        logger.debug(f"Patient internal user ID: {patient_internal_user.internal_user}")

        # Verify if the logged-in patient is the one assigned to this appointment
        if patient_internal_user.internal_user != user.get("id"):
            logger.error(f"Authorization failed - Patient ID mismatch. Expected internal_user: {patient_internal_user.internal_user}, Got: {user.get('id')}")
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to access this appointment"
            )

        # Check if appointment is booked
        if appointment.state != 'confirmed':
            return JSONResponse(
                content={"message": "Appointment has not been booked"},
                status_code=400
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
                    'routine',
                    CURRENT_TIMESTAMP
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

        # Get medical tests and medicines
        med_tests = {}
        medicines = {}
        
        # Get all tests and medicines in a single query using joins
        prescription_query = text("""
            WITH tests AS (
                SELECT DISTINCT
                    gplt.id as test_id,
                    gltt.name AS test_name,
                    gplt.test_critearea_id as test_critearea_id
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
                t.test_id,
                t.test_name,
                t.test_critearea_id,
                m.medicament,
                m.active_component
            FROM tests t
            FULL OUTER JOIN medicines m ON 1=1
            WHERE t.test_id IS NOT NULL OR m.medicament IS NOT NULL
        """)
        
        prescriptions = db.execute(prescription_query, {"appointment_id": request.appointment_id}).fetchall()
        
        # Add tests and medicines with sequential keys
        test_idx = 1
        med_idx = 1
        
        # Track unique medicines to avoid duplicates
        unique_medicines = set()
        
        for prescription in prescriptions:
            # Add test if it exists and not already added
            if prescription.test_name and not any(isinstance(v, dict) and v.get('name') == prescription.test_name for v in med_tests.values()):
                test_key = f"test_name_{test_idx}"
                # Fetch test criteria name(s) if test_critearea_id is present
                test_criteria = []
                if hasattr(prescription, 'test_critearea_id') and prescription.test_critearea_id:
                    # test_critearea_id could be a single id or a comma-separated list
                    criteria_ids = str(prescription.test_critearea_id).split(',')
                    for crit_id in criteria_ids:
                        crit_id = crit_id.strip()
                        if crit_id:
                            crit_query = text("""
                                SELECT name FROM gnuhealth_lab_test_critearea WHERE id = :crit_id
                            """)
                            crit_result = db.execute(crit_query, {"crit_id": crit_id}).fetchone()
                            if crit_result and crit_result.name:
                                test_criteria.append(crit_result.name)
                med_tests[test_key] = {
                    "name": prescription.test_name,
                    "test_critearea": test_criteria if test_criteria else None
                }
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