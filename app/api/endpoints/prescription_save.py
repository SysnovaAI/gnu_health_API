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
            # Create new prescription order
            create_query = text("""
                INSERT INTO gnuhealth_prescription_order (appointment_id, prescription_id)
                VALUES (:appointment_id, :prescription_id)
                RETURNING id
            """)
            result = db.execute(
                create_query,
                {
                    "appointment_id": appointment_id,
                    "prescription_id": prescription_id
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

            diagnosis_update_query = text("""
                UPDATE gnuhealth_patient_evaluation
                SET 
                    chief_complaint = COALESCE(:complain, chief_complaint),
                    systolic = COALESCE(:systolic, systolic),
                    diastolic = COALESCE(:diastolic, diastolic),
                    glycemia = COALESCE(:sugar_level, glycemia),
                    weight = COALESCE(:weight, weight),
                    height = COALESCE(:height, height)
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
            # First get existing prescription line
            prescription_line_query = text("""
                SELECT gpl.id
                FROM gnuhealth_prescription_line gpl
                JOIN gnuhealth_prescription_order gpo ON gpl.name = gpo.id
                WHERE gpo.appointment_id = :appointment_id
            """)
            prescription_line = db.execute(prescription_line_query, {"appointment_id": appointment_id}).fetchone()

            if not prescription_line:
                # Create new prescription line if it doesn't exist
                create_line_query = text("""
                    INSERT INTO gnuhealth_prescription_line (name)
                    VALUES (:prescription_order_id)
                    RETURNING id
                """)
                prescription_line = db.execute(
                    create_line_query,
                    {"prescription_order_id": result.id}
                ).fetchone()

            # Update tests if provided
            if update_data.med_tests:
                for test_key, test_name in update_data.med_tests.items():
                    # First check if test exists
                    check_test_query = text("""
                        SELECT id FROM gnuhealth_lab_test_type 
                        WHERE name = :test_name
                    """)
                    test = db.execute(check_test_query, {"test_name": test_name}).fetchone()

                    if not test:
                        # Generate a unique code for the test
                        test_code = f"TEST_{str(uuid.uuid4())[:8]}"
                        
                        # Create new test if it doesn't exist
                        create_test_query = text("""
                            INSERT INTO gnuhealth_lab_test_type (name, code)
                            VALUES (:test_name, :test_code)
                            RETURNING id
                        """)
                        test = db.execute(
                            create_test_query, 
                            {
                                "test_name": test_name,
                                "test_code": test_code
                            }
                        ).fetchone()

                    # Update prescription line with test
                    test_update_query = text("""
                        UPDATE gnuhealth_prescription_line
                        SET test = :test_id
                        WHERE id = :line_id
                    """)
                    
                    db.execute(
                        test_update_query,
                        {
                            "line_id": prescription_line.id,
                            "test_id": test.id
                        }
                    )

            # Update medicines if provided
            if update_data.medicine:
                for med_key, active_component in update_data.medicine.items():
                    # First check if medicine exists
                    check_med_query = text("""
                        SELECT id FROM gnuhealth_medicament 
                        WHERE active_component = :active_component
                    """)
                    medicine = db.execute(check_med_query, {"active_component": active_component}).fetchone()

                    if not medicine:
                        # Create new medicine if it doesn't exist
                        create_med_query = text("""
                            INSERT INTO gnuhealth_medicament (active_component)
                            VALUES (:active_component)
                            RETURNING id
                        """)
                        medicine = db.execute(create_med_query, {"active_component": active_component}).fetchone()

                    # Update prescription line with medicine
                    medicine_update_query = text("""
                        UPDATE gnuhealth_prescription_line
                        SET medicament = :medicament_id
                        WHERE id = :line_id
                    """)
                    
                    db.execute(
                        medicine_update_query,
                        {
                            "line_id": prescription_line.id,
                            "medicament_id": medicine.id
                        }
                    )

        # Update remarks if provided
        if update_data.remarks:
            remarks_update_query = text("""
                UPDATE gnuhealth_prescription_order
                SET notes = COALESCE(:text, notes)
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