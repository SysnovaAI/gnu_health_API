from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi.responses import JSONResponse
from ..models.base import get_db
from .appointments import get_current_user
from datetime import datetime
from pydantic import BaseModel
from typing import Dict, Optional
import uuid
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter()

class PrescriptionUpdate(BaseModel):
    Diagnosis: Optional[Dict] = None
    med_tests: Optional[Dict] = None
    medicine: Optional[Dict] = None
    remarks: Optional[Dict] = None

@router.post("/prescription-save/{appointment_id}")
def save_prescription(
    appointment_id: int,
    update_data: PrescriptionUpdate,
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
        
        appointment = db.execute(appointment_query, {"appointment_id": appointment_id}).fetchone()
        
        if not appointment:
            return JSONResponse(
                content={"message": "Appointment not found"},
                status_code=404
            )

        # Generate prescription ID and appointment name
        current_year = datetime.now().year
        prescription_id = f"PRES {current_year}/{appointment_id}"
        appointment_name = f"APP {current_year}/{appointment_id}"

        # Check if prescription order exists
        check_query = text("""
            SELECT id FROM gnuhealth_prescription_order 
            WHERE appointment_id = :appointment_id
        """)
        existing_order = db.execute(check_query, {"appointment_id": appointment_id}).fetchone()

        if not existing_order:
            # Create new prescription order with patient information
            create_query = text("""
                INSERT INTO gnuhealth_prescription_order (
                    appointment_name,
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
                    :appointment_name,
                    :appointment_id, 
                    :prescription_id,
                    :patient,
                    :healthprof,
                    CURRENT_TIMESTAMP,
                    :healthprof,
                    CURRENT_TIMESTAMP,
                    :healthprof,
                    CURRENT_TIMESTAMP,
                    :healthprof
                )
                RETURNING id
            """)
            result = db.execute(
                create_query,
                {
                    "appointment_name": appointment_name,
                    "appointment_id": appointment_id,
                    "prescription_id": prescription_id,
                    "patient": appointment.patient,
                    "healthprof": appointment.healthprof
                }
            ).fetchone()
        else:
            # Update existing prescription order
            update_query = text("""
                UPDATE gnuhealth_prescription_order
                SET 
                    appointment_name = :appointment_name,
                    prescription_id = :prescription_id,
                    write_date = CURRENT_TIMESTAMP,
                    write_uid = :healthprof
                WHERE appointment_id = :appointment_id
                RETURNING id
            """)
            result = db.execute(
                update_query,
                {
                    "appointment_name": appointment_name,
                    "prescription_id": prescription_id,
                    "appointment_id": appointment_id,
                    "healthprof": appointment.healthprof
                }
            ).fetchone()

        if not result:
            return JSONResponse(
                content={"message": "Failed to create/update prescription order"},
                status_code=500
            )

        # Update diagnosis if provided
        if update_data.Diagnosis:
            # Split blood pressure into systolic and diastolic
            blood_pressure = update_data.Diagnosis.get('blood_pressure', '').split('/')
            systolic = blood_pressure[0] if blood_pressure else None
            diastolic = blood_pressure[1] if len(blood_pressure) > 1 else None

            # First check if diagnosis exists
            check_diagnosis_query = text("""
                SELECT id FROM gnuhealth_patient_evaluation
                WHERE appointment = :appointment_id
            """)
            diagnosis = db.execute(check_diagnosis_query, {"appointment_id": appointment_id}).fetchone()

            if not diagnosis:
                # Create new diagnosis if it doesn't exist
                create_diagnosis_query = text("""
                    INSERT INTO gnuhealth_patient_evaluation (
                        appointment,
                        chief_complaint,
                        systolic,
                        diastolic,
                        glycemia,
                        weight,
                        height
                    )
                    VALUES (
                        :appointment_id,
                        :complain,
                        :systolic,
                        :diastolic,
                        :sugar_level,
                        :weight,
                        :height
                    )
                """)
                db.execute(
                    create_diagnosis_query,
                    {
                        "appointment_id": appointment_id,
                        "complain": update_data.Diagnosis.get('complain'),
                        "systolic": systolic,
                        "diastolic": diastolic,
                        "sugar_level": update_data.Diagnosis.get('sugar_level'),
                        "weight": update_data.Diagnosis.get('weight'),
                        "height": update_data.Diagnosis.get('height')
                    }
                )
            else:
                # Update existing diagnosis - use provided values even if they're null
                diagnosis_update_query = text("""
                    UPDATE gnuhealth_patient_evaluation
                    SET 
                        chief_complaint = :complain,
                        systolic = :systolic,
                        diastolic = :diastolic,
                        glycemia = :sugar_level,
                        weight = :weight,
                        height = :height
                    WHERE appointment = :appointment_id
                """)
                
                db.execute(
                    diagnosis_update_query,
                    {
                        "appointment_id": appointment_id,
                        "complain": update_data.Diagnosis.get('complain'),
                        "systolic": systolic,
                        "diastolic": diastolic,
                        "sugar_level": update_data.Diagnosis.get('sugar_level'),
                        "weight": update_data.Diagnosis.get('weight'),
                        "height": update_data.Diagnosis.get('height')
                    }
                )

        # Update medical tests and medicines if provided
        if update_data.med_tests is not None or update_data.medicine is not None:
            try:
                # First get existing prescription lines
                get_existing_lines_query = text("""
                    SELECT gpl.id, gpl.medicament, gplt.id as test_id
                    FROM gnuhealth_prescription_line gpl
                    LEFT JOIN gnuhealth_patient_lab_test gplt ON gpl.id = gplt.prescription
                    WHERE gpl.name = :prescription_order_id
                """)
                existing_lines = db.execute(
                    get_existing_lines_query,
                    {"prescription_order_id": result.id}
                ).fetchall()

                logger.debug(f"Found {len(existing_lines)} existing prescription lines")

                # Handle tests if provided
                if update_data.med_tests is not None:
                    logger.debug("Processing test updates")
                    
                    # First, delete all existing tests for this prescription
                    delete_all_tests_query = text("""
                        DELETE FROM gnuhealth_patient_lab_test
                        WHERE prescription = :prescription_id
                    """)
                    db.execute(
                        delete_all_tests_query,
                        {"prescription_id": result.id}
                    )
                    logger.debug("Deleted all existing tests")
                    
                    if update_data.med_tests:  # If new tests are provided
                        # Get unique test names to avoid duplicates
                        unique_test_names = list(set(update_data.med_tests.values()))
                        logger.debug(f"Unique test names: {unique_test_names}")
                        
                        # Add new tests
                        for test_name in unique_test_names:
                            # Check if test type exists
                            check_test_query = text("""
                                SELECT id FROM gnuhealth_lab_test_type 
                                WHERE name = :test_name
                            """)
                            test_type = db.execute(check_test_query, {"test_name": test_name}).fetchone()

                            if not test_type:
                                # Generate a unique code for the test
                                test_code = f"TEST_{str(uuid.uuid4())[:8]}"
                                logger.debug(f"Creating new test type: {test_name} with code {test_code}")
                                
                                # Create new test type
                                create_test_query = text("""
                                    INSERT INTO gnuhealth_lab_test_type (
                                        name,
                                        code
                                    )
                                    VALUES (
                                        :test_name,
                                        :test_code
                                    )
                                    RETURNING id
                                """)
                                test_type = db.execute(
                                    create_test_query,
                                    {
                                        "test_name": test_name,
                                        "test_code": test_code
                                    }
                                ).fetchone()

                            # Create new patient lab test entry
                            create_patient_test_query = text("""
                                INSERT INTO gnuhealth_patient_lab_test (
                                    prescription,
                                    name
                                )
                                VALUES (
                                    :prescription_id,
                                    :test_id
                                )
                            """)
                            db.execute(
                                create_patient_test_query,
                                {
                                    "prescription_id": result.id,
                                    "test_id": test_type.id
                                }
                            )
                            logger.debug(f"Added test: {test_name}")

                # Handle medicines if provided
                if update_data.medicine is not None:
                    logger.debug("Processing medicine updates")
                    
                    # First, delete all existing prescription lines
                    delete_all_lines_query = text("""
                        DELETE FROM gnuhealth_prescription_line
                        WHERE name = :prescription_order_id
                    """)
                    db.execute(
                        delete_all_lines_query,
                        {"prescription_order_id": result.id}
                    )
                    logger.debug("Deleted all existing prescription lines")
                    
                    if update_data.medicine:  # If new medicines are provided
                        # Get unique medicine names to avoid duplicates
                        unique_med_names = list(set(update_data.medicine.values()))
                        logger.debug(f"Unique medicine names: {unique_med_names}")
                        
                        # Add new medicines
                        for med_name in unique_med_names:
                            # Check if medicine exists
                            check_med_query = text("""
                                SELECT id FROM gnuhealth_medicament 
                                WHERE active_component = :med_name
                            """)
                            medicine = db.execute(check_med_query, {"med_name": med_name}).fetchone()

                            if not medicine:
                                # Create party entry for the medicine
                                party_code = f"MED_{str(uuid.uuid4())[:8]}"
                                logger.debug(f"Creating new medicine: {med_name} with code {party_code}")
                                
                                create_party_query = text("""
                                    INSERT INTO party_party (name, code)
                                    VALUES (:name, :code)
                                    RETURNING id
                                """)
                                party_result = db.execute(
                                    create_party_query,
                                    {
                                        "name": med_name,
                                        "code": party_code
                                    }
                                ).fetchone()

                                # Create medicine entry
                                create_med_query = text("""
                                    INSERT INTO gnuhealth_medicament (name, active_component)
                                    VALUES (:party_id, :active_component)
                                    RETURNING id
                                """)
                                medicine = db.execute(
                                    create_med_query,
                                    {
                                        "party_id": party_result.id,
                                        "active_component": med_name
                                    }
                                ).fetchone()

                            # Create new prescription line for each medicine
                            create_line_query = text("""
                                INSERT INTO gnuhealth_prescription_line (
                                    name,
                                    medicament
                                )
                                VALUES (
                                    :prescription_order_id,
                                    :medicament_id
                                )
                            """)
                            db.execute(
                                create_line_query,
                                {
                                    "prescription_order_id": result.id,
                                    "medicament_id": medicine.id
                                }
                            )
                            logger.debug(f"Added medicine: {med_name}")

            except Exception as e:
                logger.error(f"Error updating tests and medicines: {str(e)}")
                db.rollback()
                raise HTTPException(
                    status_code=500,
                    detail=f"Error updating tests and medicines: {str(e)}"
                )

        # Update remarks if provided
        if update_data.remarks:
            remarks_update_query = text("""
                UPDATE gnuhealth_prescription_order
                SET notes = :text
                WHERE appointment_id = :appointment_id
            """)
            
            db.execute(
                remarks_update_query,
                {
                    "appointment_id": appointment_id,
                    "text": update_data.remarks.get('text')
                }
            )

        # Commit all changes
        db.commit()

        return JSONResponse(
            content={
                "message": "Prescription updated successfully",
                "prescription_id": prescription_id
            },
            status_code=200
        )
        
    except Exception as e:
        db.rollback()
        return JSONResponse(
            content={"message": f"Error occurred: {str(e)}"},
            status_code=500
        ) 