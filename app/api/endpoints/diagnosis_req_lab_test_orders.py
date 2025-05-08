## New code with GET and POST Methods
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi.responses import JSONResponse
from ..models.base import get_db
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from .appointments import get_current_user

router = APIRouter(prefix="/diagnostic-center")

class TestWithSubclasses(BaseModel):
    test_id: int
    subclass_test_ids: List[int]

class NewOrderAddTest(BaseModel):
    appointment_id: Optional[int] = None
    health_prof_id: Optional[int] = None
    source: str
    urgent: bool
    tests: List[TestWithSubclasses]
    context: int


@router.get("/institute/names")
def get_appointment_details(db: Session = Depends(get_db)):
    try:
        diagnosis_query = text("""
            SELECT id, name AS diagnosis_name, is_diagnostic as diagnostic
                               FROM party_party
                               where is_diagnostic=True AND is_institution = True;
        """)
        
        result = db.execute(diagnosis_query).fetchall()

        # Convert each row to a dict safely
        diagnosis_info = [
            {
            "diagnosis_id": row.id,
            "diagnosis_name": row.diagnosis_name,
            "diagnostic": row.diagnostic
            } for row in result
            ]
        return {
            "status": True,
            "diagnosis": diagnosis_info}

    except Exception as e:
        return JSONResponse(
            content={"message": f"Error occurred: {str(e)}"},
            status_code=500
        )

@router.get("/healthprof/names")
def health_prof(db: Session = Depends(get_db)):
    try:
        health_prof = text("""        
                SELECT 
                    party_party.id AS party_party_id,
                    gnuhealth_healthprofessional.id as gnuhealth_healthprofessional_id,
                    party_party.name
                FROM party_party
                JOIN gnuhealth_healthprofessional ON party_party.id = gnuhealth_healthprofessional.name
                WHERE party_party.is_healthprof = true;
            """)
            
        result = db.execute(health_prof).fetchall()
        # Convert each row to a dict safely
        lab_test_requests = [
            {
            "party_party_id": row.party_party_id,
            "gnuhealth_healthprofessional_id": row.gnuhealth_healthprofessional_id,
            "name": row.name
            } for row in result
            ]
        return {
            "status": True,
            "lab_test_requests": lab_test_requests}

    except Exception as e:
        return JSONResponse(
            content={"message": f"Error occurred: {str(e)}"},
            status_code=500
            )


@router.get("/context/context-category")
def health_prof(db: Session = Depends(get_db)):
    try:
        context = text("""        
                SELECT 
                    gp.id AS pathology_id,
                    gp.name AS name,
                    gp.code AS code,
                    gpc.id AS main_category_id,
                    gpc.name AS main_category
                FROM gnuhealth_pathology gp
                INNER JOIN gnuhealth_pathology_category gpc ON gp.category = gpc.id;

            """)
            
        result = db.execute(context).fetchall()
        # Convert each row to a dict safely
        context = [
            {
            "id":row.pathology_id,
            "name": row.name,
            "code": row.code,
            "main_category_id": row.main_category_id,
            "main_category": row.main_category
            } for row in result
            ]
        return {
            "status": True,
            "context": context}

    except Exception as e:
        return JSONResponse(
            content={"message": f"Error occurred: {str(e)}"},
            status_code=500
            )
    
@router.get("/prescriptions/pres")
def prescriptions(pres_date: Optional[str] = None,
                  db: Session = Depends(get_db),
                  user: dict = Depends(get_current_user)
                  ):
    try:
        user_id = user.get("id")
        
        base_query = """
            SELECT 
                gpo.healthprof,
                pp.name AS doctor_name,  
                gpo.patient, 
                DATE(gpo.prescription_date) AS dates,
                gpo.prescription_date::time AS time,
                gpo.prescription_date, 
                gpo.prescription_id, 
                gpo.appointment_id, 
                patientpp.name AS patient_name
            FROM res_user ru
            JOIN party_party pp ON ru.id = pp.internal_user
            JOIN gnuhealth_healthprofessional ghp ON pp.id = ghp.name
            JOIN gnuhealth_prescription_order gpo ON ghp.id = gpo.healthprof
            JOIN gnuhealth_patient gp ON gpo.patient = gp.id 
            JOIN party_party patientpp ON gp.name = patientpp.id
            WHERE ru.id = :id
        """
        print(base_query)
        params = {"id": user_id}

        # Convert and validate date format
        if pres_date:
            try:
                # Parse and reformat to ensure it's valid
                parsed_date = datetime.strptime(pres_date, "%Y-%m-%d").date()
                base_query += " AND DATE(gpo.prescription_date) = :date"
                params["date"] = parsed_date
            except ValueError:
                return JSONResponse(
                    content={"message": "Invalid date format. Use YYYY-MM-DD."},
                    status_code=400
                )
        pres_info = db.execute(text(base_query), params).fetchall()
        
        print(pres_info)
        # Convert each row to a dict safely
        doctor_assign_pres = [
            {
            "appointment_id": row.appointment_id,
            "prescription_id": row.prescription_id,
            "patient_id": row.patient,
            "patient_name": row.patient_name,
            "healthprof_id": row.healthprof,
            "healthprof_name": row.doctor_name,
            "date":row.dates,
            "time": row.time
            } for row in pres_info
            ]
        
        return {
            "status": True,
            "prescriptions": doctor_assign_pres}

    except Exception as e:
        return JSONResponse(
            content={"message": f"Error occurred: {str(e)}"},
            status_code=500
            )


@router.post("/requests-lab-test-order-post")
def get_appointment_details(
    request: NewOrderAddTest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
    ):
    try:
        info = None
        
        info_user = db.execute(text("""
            SELECT pp.is_healthprof
            FROM res_user ru
            JOIN party_party pp ON ru.id = pp.internal_user
            WHERE ru.id = :user_id;
        """), {"user_id": user.get("id")}).fetchone()
        
        if request.appointment_id is None and info_user[0] == True:
            return JSONResponse(
                content={"message": "As a doctor, please select the appointment id which is prescribed."},
                status_code=200
            )
        if request.appointment_id:
            print(request.appointment_id)
            info = db.execute(text("""
                SELECT 
                    gpo.appointment_id, 
                    gpo.prescription_id, 
                    gpo.prescription_date,
                    gpo.healthprof, 
                    pp.name as doctor_name, 
                    gpo.patient, 
                    patientpp.name as patient_name
                FROM gnuhealth_prescription_order gpo
                JOIN gnuhealth_healthprofessional ghp ON gpo.healthprof = ghp.id
                JOIN party_party pp ON ghp.name = pp.id
                JOIN gnuhealth_patient gp ON gpo.patient = gp.id 
                JOIN party_party patientpp ON gp.name = patientpp.id
                WHERE gpo.appointment_id = :appointment_id;
            """), {"appointment_id": int(request.appointment_id)}).fetchone()
            if not info:
                return JSONResponse(
                    content={"message": "There are no prescription for this appointment."},
                    status_code=200
                )
            
            # Determine input values
            patient_id = info.patient
            doctor_id = info.healthprof
            patient_name = info.patient_name
            doctor_name = info.doctor_name
        else:
            # Determine input values
            patient_id = user["id"]
            # patient_id = 33
            patient_info = db.execute(text("""
                SELECT gp.id, pp.name
                FROM res_user ru
                JOIN party_party pp ON ru.id = pp.internal_user
                JOIN gnuhealth_patient gp ON pp.id = gp.name
                WHERE ru.id = :id;
            """), {"id": patient_id}).fetchone()
            patient_id = patient_info.id
            doctor_name = None
            doctor_id = None
            if request.health_prof_id is not None:
                doctor_info = db.execute(text("""
                    SELECT ghp.id, pp.name
                    FROM gnuhealth_healthprofessional ghp
                    JOIN party_party pp ON ghp.name = pp.id
                    WHERE ghp.id = :id;
                """), {"id": int(request.health_prof_id)}).fetchone()
                if doctor_info is None:
                    return JSONResponse(
                    content={"message": "There are no healthprof for this ID"},
                    status_code=200)
                
                doctor_name = doctor_info.name
                doctor_id = doctor_info.id
            patient_name = patient_info.name

        # Get current time from server
        current_time = db.execute(text("SELECT NOW() AT TIME ZONE 'Asia/Dhaka';")).fetchone()[0]

        # Insert lab tests
        for test in request.tests:
            for subclass_id in test.subclass_test_ids:
                insert_query = """
                    INSERT INTO gnuhealth_patient_lab_test (
                        date, doctor_id, patient_id, name, source_type, urgent, context, test_critearea_id
                    ) VALUES (
                        :date, :doctor_id, :patient_id, :name, :source, :urgent, :context, :test_critearea_id
                    )
                """
                db.execute(text(insert_query), {
                    "date": current_time,
                    "doctor_id": doctor_id,
                    "patient_id": patient_id,
                    "name": test.test_id,
                    "source": request.source,
                    "urgent": request.urgent,
                    "context": request.context,
                    "test_critearea_id": subclass_id
                })

        db.commit()

        response = {
            "status": True,
            "patient_id": patient_id,
            "patient_name": patient_name,
            "healthprof_id": doctor_id,
            "doctor_name": doctor_name,
            "message": "Added the Tests"
        }
            
        return response

    except Exception as e:
        return JSONResponse(
            content={"message": f"Error occurred: {str(e)}"},
            status_code=500
        )


@router.get("/requests/lab-test")
def get_appointment_details(db: Session = Depends(get_db)):
    try:
        lab_test_requests = text("""        
             SELECT 
                gplt.id,
                gltt.id AS test_type_id,
                gltt.name AS test_type,
                DATE(gplt.date),
                gplt.date::time AS time,
                gplt.source_type,
                gplt.patient_id AS patient_id,
                pat_party.name AS patient_name,
                gplt.doctor_id AS healthprof_id,
                doc_party.name AS healthprof_name,
                gplt.context,
                gplt.state,
                gplt.test_critearea_id,
                gltc.name as test_criteria_name,
                gltc.code as test_criteria_code   
                                
            FROM gnuhealth_patient_lab_test gplt
            JOIN gnuhealth_healthprofessional gh ON gh.id = gplt.doctor_id
            JOIN party_party doc_party ON doc_party.id = gh.name
            JOIN gnuhealth_patient gp ON gp.id = gplt.patient_id
            JOIN party_party pat_party ON pat_party.id = gp.name
            JOIN gnuhealth_lab_test_type gltt ON gltt.id = gplt.name
            join gnuhealth_lab_test_critearea gltc ON gplt.test_critearea_id = gltc.id

        """)
        
        result = db.execute(lab_test_requests).fetchall()

        # Convert each row to a dict safely
        lab_test_requests = [
            {
            "id": row.id,
            "categories_id": row.test_type_id,
            "categories_type": row.test_type,
            "date": row.date,
            "time": row.time,
            "source": row.source_type,
            "source_name_id": row.patient_id,
            "source_name": row.patient_name,
            "healthprof_id": row.healthprof_id,
            "healthprof_name": row.healthprof_name,
            "context": row.context,
            "state": row.state,
            "test_criteria_id": row.test_critearea_id,
            "test_criteria_name": row.test_criteria_name,
            "test_criteria_code": row.test_criteria_code
            } for row in result
            ]
        return {
            "status": True,
            "lab_test_requests": lab_test_requests}

    except Exception as e:
        return JSONResponse(
            content={"message": f"Error occurred: {str(e)}"},
            status_code=500
        )
    


@router.get("/requests/lab-test-specific-patient")
def get_appointment_details(test_date: Optional[str] = None,
                            db: Session = Depends(get_db),
                            user: dict = Depends(get_current_user)
    ):
    try:
        user_id = user.get("id")
        # user_id= 151
        base_query = """       
                    SELECT 
                        gplt.id,
                        DATE(gplt.date),
                        gplt.date::time AS time,
                        gplt.name as categories_id,                
                        gltt.code as categories_code,
                        gltt.name as categories_name,
                        gplt.source_type,
                        gplt.patient_id AS patient_id,
                        pp.name as patient_name,
                        gplt.doctor_id AS healthprof_id,
                        healthpp.name as healthprof_name,
                        gplt.context,
                        gpathology.code as context_code,
                        gpathology.name as context_name,
                        gpc.name as main_category,
                        gplt.state,
                        gplt.test_critearea_id,
                        gltc.code as criterea_code,
                        gltc.name as criterea_name
                                                    
                    FROM res_user ru
                    JOIN party_party pp ON ru.id = pp.internal_user
                    JOIN gnuhealth_patient gp ON pp.id = gp.name
                    JOIN gnuhealth_patient_lab_test gplt on gp.id = gplt.patient_id 
                    join gnuhealth_lab_test_type gltt on gplt.name = gltt.id
                    join gnuhealth_healthprofessional gh on gplt.doctor_id = gh.id
                    join party_party healthpp on gh.name = healthpp.id
                    join gnuhealth_pathology as gpathology on gplt.context = gpathology.id
                    join gnuhealth_pathology_category gpc on gpathology.category = gpc.id
                    join gnuhealth_lab_test_critearea gltc on gplt.test_critearea_id = gltc.id
                    where ru.id = :id
        """
        
        params = {"id": user_id}

        # Convert and validate date format
        if test_date:
            try:
                # Parse and reformat to ensure it's valid
                parsed_date = datetime.strptime(test_date, "%Y-%m-%d").date()
                base_query += " AND DATE(gplt.date) = :date"
                params["date"] = parsed_date
            except ValueError:
                return JSONResponse(
                    content={"message": "Invalid date format. Use YYYY-MM-DD."},
                    status_code=400
                )
        test_info = db.execute(text(base_query), params).fetchall()
 
        # Convert each row to a dict safely
        patient_lab_test_requests = [
            {
            "id": row.id,
            "categories_id": row.categories_id,
            "categories_code": row.categories_code,
            "categories_name": row.categories_name,
            "date": row.date,
            "time": row.time,
            "source": row.source_type,
            "patient_id": row.patient_id,
            "patient_name": row.patient_name,
            "healthprof_id": row.healthprof_id,
            "healthprof_name": row.healthprof_name,
            "context_id": row.context,
            "context_code": row.context_code,
            "context_name": row.context_name,
            "main_category": row.main_category,
            "state": row.state,
            "test_criteria_id": row.test_critearea_id,
            "criterea_code": row.criterea_code,
            "criteria_name": row.criterea_name
            } for row in test_info
            ]
        return {
            "status": True,
            "patient_lab_test_requests": patient_lab_test_requests}

    except Exception as e:
        return JSONResponse(
            content={"message": f"Error occurred: {str(e)}"},
            status_code=500
        )