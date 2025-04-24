from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi.responses import JSONResponse
from ..models.base import get_db
from .appointments import get_current_user
from pydantic import BaseModel
import uuid

router = APIRouter()

class AppointmentDetailsRequest(BaseModel):
    appointment_id: int

@router.post("/prescription-header")
def get_appointment_details(
    request: AppointmentDetailsRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    try:
        # Initialize response structure with null values
        response = {
            "appointment_id": request.appointment_id,
            "patient_details": None,
            "doctor_details": None,
            "Diagnosis": None,
            "medical_history": None,
            "med_tests": None,
            "medicine": None,
            "remarks": None
        }

        # First get the patient ID from the appointment
        appointment_query = text("""
            SELECT 
                ga.id,
                ga.patient,
                ga.healthprof
            FROM gnuhealth_appointment ga
            WHERE ga.id = :appointment_id
        """)
        
        appointment = db.execute(appointment_query, {"appointment_id": request.appointment_id}).fetchone()
        
        if not appointment:
            return JSONResponse(content=response, status_code=200)

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
        
        if diagnosis:
            diagnosis_details = {
                "complain": diagnosis.chief_complaint,
                "blood_pressure": f"{diagnosis.systolic}/80" if diagnosis.systolic else None,
                "sugar_level": diagnosis.glycemia,
                "weight": diagnosis.weight,
                "height": diagnosis.height
            }
            response["Diagnosis"] = diagnosis_details
            
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
        
        if patient:
            # Build patient details dynamically based on available fields
            patient_details = {
                "name": patient.patient_name,
                "gender": patient.gender,
                "mobile_number": patient.mobile_number,
                "email": None  # Will be updated if found
            }

            # Get patient email if internal_user exists
            if patient.internal_user:
                patient_user_query = text("""
                    SELECT email
                    FROM res_user
                    WHERE id = :internal_user
                """)
                patient_user = db.execute(patient_user_query, {"internal_user": patient.internal_user}).fetchone()
                if patient_user:
                    patient_details["email"] = patient_user.email

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

            response["patient_details"] = patient_details
            
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
        
        if doctor:
            doctor_details = {
                "name": doctor.doctor_name,
                "specialization": doctor.main_specialty,
                "mobile_number": doctor.mobile_number,
                "email": doctor.email
            }
            response["doctor_details"] = doctor_details

        # Get medical tests and medicines
        med_tests = {}
        medicines = {}
        
        # Get all tests and medicines in a single query using joins
        prescription_query = text("""
            SELECT 
                gpl.medicament,
                gm.active_component,
                gpl.test,
                gltt.name AS test_name
            FROM gnuhealth_prescription_order gpo
            JOIN gnuhealth_prescription_line gpl ON gpl.name = gpo.id
            LEFT JOIN gnuhealth_medicament gm ON gm.id = gpl.medicament
            LEFT JOIN gnuhealth_lab_test_type gltt ON gltt.id = gpl.test
            WHERE gpo.appointment_id = :appointment_id
        """)
        
        prescriptions = db.execute(prescription_query, {"appointment_id": request.appointment_id}).fetchall()
        
        if prescriptions:
            # Add tests and medicines with sequential keys
            test_idx = 1
            med_idx = 1
            
            for prescription in prescriptions:
                # Add test if it exists
                if prescription.test_name:
                    test_key = f"test_name_{test_idx}"
                    med_tests[test_key] = prescription.test_name
                    test_idx += 1
                    
                # Add medicine if it exists
                if prescription.active_component:
                    med_key = f"medicine_{med_idx}"
                    medicines[med_key] = prescription.active_component
                    med_idx += 1

            if med_tests:
                response["med_tests"] = med_tests
            if medicines:
                response["medicine"] = medicines

        # Get remarks from gnuhealth_prescription_order
        remarks_query = text("""
            SELECT notes
            FROM gnuhealth_prescription_order
            WHERE appointment_id = :appointment_id
        """)
        
        prescription_order = db.execute(remarks_query, {"appointment_id": request.appointment_id}).fetchone()
        
        if prescription_order and prescription_order.notes:
            response["remarks"] = {"text": prescription_order.notes}
        
        return JSONResponse(content=response, status_code=200)
        
    except Exception as e:
        return JSONResponse(
            content={"message": f"Error occurred: {str(e)}"},
            status_code=500
        ) 