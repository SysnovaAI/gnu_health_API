from fastapi import APIRouter, Depends, HTTPException, Header, status, Path
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from jose import jwt, JWTError
import logging
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from ..models.base import get_db, SECRET_KEY
import traceback

# Setup logging
logger = logging.getLogger(__name__)
router = APIRouter()

# ---- Models ----
class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_type: str
    quantity: int
    price_per_unit: float
    total_price: float
    product_description: Optional[str] = None
    product_code: Optional[str] = None

class OrderResponse(BaseModel):
    id: int
    user_id: int
    order_date: str
    status: str
    total_amount: float
    payment_method: str
    payment_status: str
    shipping_address: str
    notes: Optional[str] = None
    items: List[OrderItemResponse] = []

# ---- Endpoints ----

@router.post("", response_model=List[OrderResponse])
def get_user_orders(
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Get all orders for the current user with detailed product information
    """
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
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail=f"Invalid token: {str(e)}"
        )
    
    try:
        # Get all orders for the user
        orders_query = """
            SELECT * FROM ecom_orders 
            WHERE user_id = :user_id
            ORDER BY order_date DESC
        """
        orders = db.execute(text(orders_query), {"user_id": user_id}).fetchall()
        
        if not orders:
            return []
        
        result = []
        
        for order in orders:
            # Get order items with product details
            items_query = """
                SELECT 
                    eoi.id, 
                    eoi.product_id, 
                    eoi.quantity, 
                    eoi.price_per_unit, 
                    eoi.total_price,
                    pt.name as product_name,
                    pt.type as product_type
                FROM ecom_order_items eoi
                JOIN product_product pp ON eoi.product_id = pp.id
                JOIN product_template pt ON pp.template = pt.id
                WHERE eoi.order_id = :order_id
            """
            items = db.execute(text(items_query), {"order_id": order.id}).fetchall()
            
            # Format order items
            order_items = []
            for item in items:
                order_items.append({
                    "id": item.id,
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "product_type": item.product_type,
                    "quantity": item.quantity,
                    "price_per_unit": float(item.price_per_unit),
                    "total_price": float(item.total_price)
                })
            
            # Format order data
            order_data = {
                "id": order.id,
                "user_id": order.user_id,
                "order_date": order.order_date.isoformat() if order.order_date else None,
                "status": order.status,
                "total_amount": float(order.total_amount),
                "payment_method": order.payment_method,
                "payment_status": order.payment_status,
                "shipping_address": order.shipping_address,
                "notes": order.notes,
                "items": order_items
            }
            
            result.append(order_data)
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching user orders: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch orders: {str(e)}"
        )

@router.post("/{order_id}", response_model=OrderResponse)
def get_order_details(
    order_id: int = Path(..., title="The ID of the order to retrieve", gt=0),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific order.
    This is a public endpoint that doesn't require authentication.
    """
    try:
        logger.info(f"Processing request for order ID: {order_id}")
        
        # Get order details
        order_query = """
            SELECT * FROM ecom_orders 
            WHERE id = :order_id
        """
        order = db.execute(text(order_query), {"order_id": order_id}).fetchone()
        
        if not order:
            logger.warning(f"Order with ID {order_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order with ID {order_id} not found"
            )
        
        logger.info(f"Found order: {order}")
        
        # Get order items with product details
        items_query = """
            SELECT 
                eoi.id, 
                eoi.product_id, 
                eoi.quantity, 
                eoi.price_per_unit, 
                eoi.total_price,
                pt.name as product_name,
                pt.type as product_type,
                pp.description as product_description,
                pt.code as product_code
            FROM ecom_order_items eoi
            JOIN product_product pp ON eoi.product_id = pp.id
            JOIN product_template pt ON pp.template = pt.id
            WHERE eoi.order_id = :order_id
        """
        items = db.execute(text(items_query), {"order_id": order_id}).fetchall()
        
        logger.info(f"Found {len(items) if items else 0} order items")
        
        # Format order items
        order_items = []
        for item in items:
            order_items.append({
                "id": item.id,
                "product_id": item.product_id,
                "product_name": item.product_name,
                "product_type": item.product_type,
                "quantity": item.quantity,
                "price_per_unit": float(item.price_per_unit),
                "total_price": float(item.total_price),
                # Additional product details
                "product_description": item.product_description,
                "product_code": item.product_code
            })
        
        # Format order data
        order_data = {
            "id": order.id,
            "user_id": order.user_id,
            "order_date": order.order_date.isoformat() if order.order_date else None,
            "status": order.status,
            "total_amount": float(order.total_amount),
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "shipping_address": order.shipping_address,
            "notes": order.notes,
            "items": order_items
        }
        
        logger.info("Successfully formatted order data")
        return order_data
        
    except HTTPException:
        raise
        
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error fetching order details: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch order details: {str(e)}"
        )
