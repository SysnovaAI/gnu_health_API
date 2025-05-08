from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel
import logging
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from ..models.base import get_db
import traceback

# Setup logging
logger = logging.getLogger(__name__)
router = APIRouter()

# Models
class LabTestOrderCreate(BaseModel):
    lab_test_ids: List[int]
    notes: Optional[str] = None

class LabTestOrderResponse(BaseModel):
    order_id: int
    message: str

@router.post("/lab-test-order", response_model=LabTestOrderResponse)
def create_lab_test_order(
    order_data: LabTestOrderCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new order for lab tests.
    
    1. Validates lab test IDs exist in gnuhealth_patient_lab_test
    2. Creates an order in ecom_orders
    3. Creates order items in ecom_order_items with is_test=true
    """
    try:
        lab_test_ids = tuple(order_data.lab_test_ids)
        
        if not lab_test_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No lab test IDs provided"
            )
        
        # Validate lab test IDs exist in gnuhealth_patient_lab_test and get the user_id
        if len(lab_test_ids) == 1:
            # Special case for single item
            validation_query = """
                SELECT gplt.id, gplt.patient_id, gplt.name, pp.internal_user AS res_user_id
                FROM gnuhealth_patient_lab_test gplt
                JOIN gnuhealth_patient gp ON gplt.patient_id = gp.id
                JOIN party_party pp ON gp.name = pp.id
                WHERE gplt.id = :test_id
            """
            lab_tests = db.execute(
                text(validation_query), 
                {"test_id": lab_test_ids[0]}
            ).fetchall()
        else:
            # Handle multiple items
            placeholders = ", ".join([f":id{i}" for i in range(len(lab_test_ids))])
            params = {}
            
            for i, test_id in enumerate(lab_test_ids):
                params[f"id{i}"] = test_id
                
            validation_query = f"""
                SELECT gplt.id, gplt.patient_id, gplt.name, pp.internal_user AS res_user_id
                FROM gnuhealth_patient_lab_test gplt
                JOIN gnuhealth_patient gp ON gplt.patient_id = gp.id
                JOIN party_party pp ON gp.name = pp.id
                WHERE gplt.id IN ({placeholders})
            """
            lab_tests = db.execute(text(validation_query), params).fetchall()
        
        if not lab_tests or len(lab_tests) != len(lab_test_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more lab test IDs not found"
            )
        
        # Get res_user ID from the first lab test
        # Assuming all lab tests belong to the same patient
        res_user_id = lab_tests[0].res_user_id if lab_tests and hasattr(lab_tests[0], 'res_user_id') else None
        
        if not res_user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Could not find associated user for patient"
            )
        
        # Create new order - set required fields with default values where necessary
        order_query = """
            INSERT INTO ecom_orders 
            (user_id, order_date, status, total_amount, payment_method, payment_status, shipping_address, notes)
            VALUES (:user_id, CURRENT_TIMESTAMP, 'pending', 0, 'N/A', 'pending', 'N/A', :notes)
            RETURNING id
        """
        
        order_result = db.execute(
            text(order_query),
            {
                "user_id": res_user_id,  # Use res_user_id as user_id
                "notes": order_data.notes
            }
        )
        order_id = order_result.scalar()
        
        # Create order items for each lab test
        for test in lab_tests:
            order_item_query = """
                INSERT INTO ecom_order_items
                (order_id, product_id, quantity, price_per_unit, total_price, created_at, lab_test_id, is_test)
                VALUES (:order_id, NULL, 1, 0, 0, CURRENT_TIMESTAMP, :lab_test_id, true)
            """
            
            db.execute(
                text(order_item_query),
                {
                    "order_id": order_id,
                    "lab_test_id": test.id
                }
            )
        
        # Commit the transaction
        db.commit()
        
        return {
            "order_id": order_id,
            "message": "Lab test order created successfully"
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions (no need to rollback)
        raise
        
    except Exception as e:
        db.rollback()
        error_trace = traceback.format_exc()
        logger.error(f"Lab test order creation error: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create lab test order: {str(e)}"
        )
