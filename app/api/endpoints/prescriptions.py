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
            return JSONResponse(
                content={"message": "Appointment not found"},
                status_code=404
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
            "Diagnosis": diagnosis_details if diagnosis_details else None
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