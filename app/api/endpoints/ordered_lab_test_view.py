from fastapi import APIRouter, Depends, HTTPException, Header, status, Body, Request
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from jose import jwt, JWTError
import logging
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from ..models.base import get_db, SECRET_KEY
import traceback
import json

# Setup logging
logger = logging.getLogger(__name__)
router = APIRouter()

# ---- Models ----
class TestTypeInfo(BaseModel):
    id: int
    code: Optional[str] = None
    name: Optional[str] = None

class CriteareaInfo(BaseModel):
    id: int
    name: Optional[str] = None
    code: Optional[str] = None
    normal_range: Optional[str] = None
    units: Optional[int] = None
    lower_limit: Optional[float] = None
    upper_limit: Optional[float] = None
    result: Optional[float] = None
    result_text: Optional[str] = None

class LabTestItemResponse(BaseModel):
    id: int
    order_id: int
    lab_test_id: Optional[int] = None
    quantity: int
    price_per_unit: float
    total_price: float
    test_name: Optional[int] = None
    test_type_info: Optional[TestTypeInfo] = None
    test_date: Optional[str] = None
    test_state: Optional[str] = None
    doctor_name: Optional[str] = None
    test_critearea_id: Optional[int] = None
    test_critearea_info: Optional[CriteareaInfo] = None

class LabTestOrderResponse(BaseModel):
    id: int
    user_id: int
    order_date: str
    status: str
    total_amount: float
    payment_method: Optional[str] = None
    payment_status: str
    shipping_address: Optional[str] = None
    notes: Optional[str] = None
    items: List[LabTestItemResponse] = []

# ---- Endpoints ----

@router.post("/lab-test-orders")
async def get_user_lab_test_orders(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Get all lab test orders for the current user with detailed test information
    """
    logger.info("POST /lab-test-orders endpoint called")
    
    # Verify token and get user ID
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Missing or invalid authorization header"
        )
        
    token = authorization.replace("Bearer ", "")
    
    try:
        # Decode JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid token: User ID not found"
            )
        
        logger.info(f"Token verified, user_id: {user_id}")
    except JWTError as e:
        logger.error(f"JWT token verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail=f"Invalid token: {str(e)}"
        )
    
    result = []
    
    try:
        # Step 1: First get all orders for the user
        logger.info(f"Fetching all orders for user ID: {user_id}")
        all_orders_query = """
            SELECT * 
            FROM ecom_orders 
            WHERE user_id = :user_id
            ORDER BY order_date DESC
        """
        all_orders = db.execute(text(all_orders_query), {"user_id": user_id}).fetchall()
        
        if not all_orders:
            logger.info(f"No orders found for user ID: {user_id}")
            return []
            
        logger.info(f"Found {len(all_orders)} orders for user ID: {user_id}")
        
        # Step 2: Filter for test orders
        for order in all_orders:
            try:
                order_id = order.id
                
                # First check if this order has any test items
                test_items_check_query = """
                    SELECT COUNT(*) as test_count
                    FROM ecom_order_items
                    WHERE order_id = :order_id AND is_test = true
                """
                test_count_result = db.execute(
                    text(test_items_check_query), 
                    {"order_id": order_id}
                ).fetchone()
                
                test_count = test_count_result.test_count if test_count_result else 0
                
                # Also check if the notes contain "Test"
                has_test_in_notes = order.notes and "Test" in order.notes
                
                # Skip if neither condition is met
                if test_count == 0 and not has_test_in_notes:
                    continue
                
                logger.info(f"Processing lab test order ID: {order_id}")
                
                # Get order items with lab test details
                items_query = """
                    SELECT 
                        eoi.id, 
                        eoi.order_id,
                        eoi.quantity, 
                        COALESCE(eoi.price_per_unit, 0) as price_per_unit, 
                        COALESCE(eoi.total_price, 0) as total_price,
                        eoi.lab_test_id,
                        gplt.name AS test_name,
                        gplt.date AS test_date,
                        gplt.state AS test_state,
                        gplt.test_critearea_id,
                        pp.name AS doctor_name
                    FROM ecom_order_items eoi
                    LEFT JOIN gnuhealth_patient_lab_test gplt ON eoi.lab_test_id = gplt.id
                    LEFT JOIN gnuhealth_healthprofessional hp ON gplt.doctor_id = hp.id
                    LEFT JOIN party_party pp ON hp.name = pp.id
                    WHERE eoi.order_id = :order_id
                    AND eoi.is_test = true
                """
                items = db.execute(text(items_query), {"order_id": order_id}).fetchall()
                
                # Format order items
                order_items = []
                for item in items:
                    # Get test type info
                    test_type_info = None
                    if item.test_name:
                        test_type_query = """
                            SELECT id, code, name
                            FROM gnuhealth_lab_test_type
                            WHERE id = :test_type_id
                        """
                        test_type_result = db.execute(
                            text(test_type_query),
                            {"test_type_id": item.test_name}
                        ).fetchone()
                        
                        if test_type_result:
                            test_type_info = {
                                "id": test_type_result.id,
                                "code": test_type_result.code,
                                "name": test_type_result.name
                            }
                    
                    # Get test critearea info
                    critearea_info = None
                    if item.test_critearea_id:
                        critearea_query = """
                            SELECT 
                                id, name, code, normal_range, units, 
                                lower_limit, upper_limit, result, result_text
                            FROM gnuhealth_lab_test_critearea
                            WHERE id = :critearea_id
                        """
                        critearea_result = db.execute(
                            text(critearea_query),
                            {"critearea_id": item.test_critearea_id}
                        ).fetchone()
                        
                        if critearea_result:
                            critearea_info = {
                                "id": critearea_result.id,
                                "name": critearea_result.name,
                                "code": critearea_result.code,
                                "normal_range": critearea_result.normal_range,
                                "units": critearea_result.units,
                                "lower_limit": float(critearea_result.lower_limit) if critearea_result.lower_limit is not None else None,
                                "upper_limit": float(critearea_result.upper_limit) if critearea_result.upper_limit is not None else None,
                                "result": float(critearea_result.result) if critearea_result.result is not None else None,
                                "result_text": critearea_result.result_text
                            }
                    
                    # Format the item data
                    item_data = {
                        "id": item.id,
                        "order_id": item.order_id,
                        "lab_test_id": item.lab_test_id,
                        "quantity": item.quantity,
                        "price_per_unit": float(item.price_per_unit),
                        "total_price": float(item.total_price),
                        "test_name": item.test_name,
                        "test_type_info": test_type_info,
                        "test_date": item.test_date.isoformat() if item.test_date else None,
                        "test_state": item.test_state,
                        "doctor_name": item.doctor_name,
                        "test_critearea_id": item.test_critearea_id,
                        "test_critearea_info": critearea_info
                    }
                    order_items.append(item_data)
                
                # Format order data
                order_data = {
                    "id": order.id,
                    "user_id": order.user_id,
                    "order_date": order.order_date.isoformat() if order.order_date else None,
                    "status": order.status,
                    "total_amount": float(order.total_amount) if order.total_amount is not None else 0.0,
                    "payment_method": order.payment_method,
                    "payment_status": order.payment_status,
                    "shipping_address": order.shipping_address,
                    "notes": order.notes,
                    "items": order_items
                }
                
                result.append(order_data)
                logger.info(f"Successfully processed order ID: {order_id}")
                
            except Exception as item_err:
                logger.error(f"Error processing order {order.id}: {str(item_err)}")
                logger.error(traceback.format_exc())
                # Continue with other orders instead of failing completely
                continue
        
        logger.info(f"Returning {len(result)} lab test orders")
        return result
        
    except Exception as e:
        logger.error(f"Error fetching lab test orders: {str(e)}")
        logger.error(traceback.format_exc())
        # Return the error details in the response instead of a generic message
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch lab test orders: {str(e)}"
        )

@router.post("/lab-test-orders/{order_id}")
async def get_lab_test_order_details(
    order_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific lab test order.
    This is a public endpoint that doesn't require authentication.
    """
    try:
        logger.info(f"Processing request for lab test order ID: {order_id}")
        
        # Get order details
        order_query = """
            SELECT * FROM ecom_orders 
            WHERE id = :order_id
        """
        order = db.execute(
            text(order_query), 
            {"order_id": order_id}
        ).fetchone()
        
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lab test order with ID {order_id} not found"
            )
        
        # Get order items with lab test details
        items_query = """
            SELECT 
                eoi.id, 
                eoi.order_id,
                eoi.quantity, 
                COALESCE(eoi.price_per_unit, 0) as price_per_unit, 
                COALESCE(eoi.total_price, 0) as total_price,
                eoi.lab_test_id,
                gplt.name AS test_name,
                gplt.date AS test_date,
                gplt.state AS test_state,
                gplt.test_critearea_id,
                pp.name AS doctor_name
            FROM ecom_order_items eoi
            LEFT JOIN gnuhealth_patient_lab_test gplt ON eoi.lab_test_id = gplt.id
            LEFT JOIN gnuhealth_healthprofessional hp ON gplt.doctor_id = hp.id
            LEFT JOIN party_party pp ON hp.name = pp.id
            WHERE eoi.order_id = :order_id
            AND eoi.is_test = true
        """
        items = db.execute(text(items_query), {"order_id": order_id}).fetchall()
        
        # Format order items
        order_items = []
        for item in items:
            # Get test type info
            test_type_info = None
            if item.test_name:
                test_type_query = """
                    SELECT id, code, name
                    FROM gnuhealth_lab_test_type
                    WHERE id = :test_type_id
                """
                test_type_result = db.execute(
                    text(test_type_query),
                    {"test_type_id": item.test_name}
                ).fetchone()
                
                if test_type_result:
                    test_type_info = {
                        "id": test_type_result.id,
                        "code": test_type_result.code,
                        "name": test_type_result.name
                    }
            
            # Get test critearea info
            critearea_info = None
            if item.test_critearea_id:
                critearea_query = """
                    SELECT 
                        id, name, code, normal_range, units, 
                        lower_limit, upper_limit, result, result_text
                    FROM gnuhealth_lab_test_critearea
                    WHERE id = :critearea_id
                """
                critearea_result = db.execute(
                    text(critearea_query),
                    {"critearea_id": item.test_critearea_id}
                ).fetchone()
                
                if critearea_result:
                    critearea_info = {
                        "id": critearea_result.id,
                        "name": critearea_result.name,
                        "code": critearea_result.code,
                        "normal_range": critearea_result.normal_range,
                        "units": critearea_result.units,
                        "lower_limit": float(critearea_result.lower_limit) if critearea_result.lower_limit is not None else None,
                        "upper_limit": float(critearea_result.upper_limit) if critearea_result.upper_limit is not None else None,
                        "result": float(critearea_result.result) if critearea_result.result is not None else None,
                        "result_text": critearea_result.result_text
                    }
            
            # Format the item data
            item_data = {
                "id": item.id,
                "order_id": item.order_id,
                "lab_test_id": item.lab_test_id,
                "quantity": item.quantity,
                "price_per_unit": float(item.price_per_unit),
                "total_price": float(item.total_price),
                "test_name": item.test_name,
                "test_type_info": test_type_info,
                "test_date": item.test_date.isoformat() if item.test_date else None,
                "test_state": item.test_state,
                "doctor_name": item.doctor_name,
                "test_critearea_id": item.test_critearea_id,
                "test_critearea_info": critearea_info
            }
            order_items.append(item_data)
        
        # Format order data
        order_data = {
            "id": order.id,
            "user_id": order.user_id,
            "order_date": order.order_date.isoformat() if order.order_date else None,
            "status": order.status,
            "total_amount": float(order.total_amount) if order.total_amount is not None else 0.0,
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "shipping_address": order.shipping_address,
            "notes": order.notes,
            "items": order_items
        }
        
        logger.info("Successfully formatted lab test order data")
        return order_data
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error fetching lab test order details: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch lab test order details: {str(e)}"
        )
