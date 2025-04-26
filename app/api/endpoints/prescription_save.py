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

        # Generate prescription ID
        current_year = datetime.now().year
        prescription_id = f"PRES {current_year}/{appointment_id}"

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
                    appointment_id, 
                    prescription_id,
                    patient,
                    healthprof
                )
                VALUES (
                    :appointment_id, 
                    :prescription_id,
                    :patient,
                    :healthprof
                )
                RETURNING id
            """)
            result = db.execute(
                create_query,
                {
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
                SET prescription_id = :prescription_id
                WHERE appointment_id = :appointment_id
                RETURNING id
            """)
            result = db.execute(
                update_query,
                {
                    "prescription_id": prescription_id,
                    "appointment_id": appointment_id
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
        if update_data.med_tests or update_data.medicine:
            # Handle tests if provided
            if update_data.med_tests:
                for test_key, test_name in update_data.med_tests.items():
                    # Check if test type exists
                    check_test_query = text("""
                        SELECT id FROM gnuhealth_lab_test_type 
                        WHERE name = :test_name
                    """)
                    test_type = db.execute(check_test_query, {"test_name": test_name}).fetchone()

                    if not test_type:
                        # Generate a unique code for the test
                        test_code = f"TEST_{str(uuid.uuid4())[:8]}"
                        
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

            # Handle medicines if provided
            if update_data.medicine:
                # Create a set to track unique medicines
                unique_medicines = set()
                
                for med_key, active_component in update_data.medicine.items():
                    # Skip if we've already processed this medicine
                    if active_component in unique_medicines:
                        continue
                    
                    unique_medicines.add(active_component)
                    
                    # Check if medicine exists
                    check_med_query = text("""
                        SELECT id FROM gnuhealth_medicament 
                        WHERE active_component = :active_component
                    """)
                    medicine = db.execute(check_med_query, {"active_component": active_component}).fetchone()

                    if not medicine:
                        # Create new medicine
                        create_med_query = text("""
                            INSERT INTO gnuhealth_medicament (
                                active_component
                            )
                            VALUES (
                                :active_component
                            )
                            RETURNING id
                        """)
                        medicine = db.execute(
                            create_med_query,
                            {"active_component": active_component}
                        ).fetchone()

                    # Create new prescription line
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