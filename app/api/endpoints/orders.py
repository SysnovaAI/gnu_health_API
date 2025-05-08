from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import List, Optional
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from jose import jwt, JWTError
from ..models.base import get_db, SECRET_KEY
import logging
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

logger = logging.getLogger(__name__)
router = APIRouter()

class OrderCreate(BaseModel):
    cart_item_ids: List[int]
    shipping_address: str
    notes: Optional[str] = None
    payment_method: str = "done"  # Default to "done" for now

class OrderResponse(BaseModel):
    order_id: int
    message: str

@router.post("/create", response_model=OrderResponse)
def create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Create a new order from cart items.
    
    1. Validates user from JWT token
    2. Gets cart items by IDs
    3. Creates an order in ecom_orders
    4. Creates order items in ecom_order_items
    5. Marks cart items as processed (order_pressed = true)
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
    
    # Get cart items by IDs
    try:
        cart_item_ids = tuple(order_data.cart_item_ids)
        
        if not cart_item_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No cart items provided"
            )
        
        # First, check if any cart items are already deleted or processed
        if len(cart_item_ids) == 1:
            # Special case for single item
            validation_query = """
                SELECT id, is_delet, order_pressed 
                FROM cart_items
                WHERE id = :item_id 
                AND patient_id = :user_id
                AND (is_delet = true OR order_pressed = true)
            """
            invalid_items = db.execute(
                text(validation_query), 
                {"item_id": cart_item_ids[0], "user_id": user_id}
            ).fetchall()
        else:
            # Handle multiple items
            placeholders = ", ".join([f":id{i}" for i in range(len(cart_item_ids))])
            params = {"user_id": user_id}
            
            for i, item_id in enumerate(cart_item_ids):
                params[f"id{i}"] = item_id
                
            validation_query = f"""
                SELECT id, is_delet, order_pressed 
                FROM cart_items
                WHERE id IN ({placeholders})  
                AND patient_id = :user_id
                AND (is_delet = true OR order_pressed = true)
            """
            invalid_items = db.execute(text(validation_query), params).fetchall()
        
        # If any invalid items found, return error with their IDs
        if invalid_items:
            invalid_ids = [item.id for item in invalid_items]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot create order. Cart items {invalid_ids} are already deleted or processed"
            )
        
        # Get cart items with proper SQL query
        if len(cart_item_ids) == 1:
            # Special case for single item
            cart_query = """
                SELECT ci.*, pp.id as product_id, plp.list_price as price_per_unit
                FROM cart_items ci
                JOIN product_product pp ON ci.product_id = pp.id
                JOIN product_template pt ON pp.template = pt.id
                JOIN product_list_price plp ON plp.template = pt.id
                WHERE ci.id = :item_id 
                AND ci.patient_id = :user_id
                AND (ci.is_delet IS NULL OR ci.is_delet = false)
                AND (ci.order_pressed IS NULL OR ci.order_pressed = false)
            """
            cart_items = db.execute(
                text(cart_query), 
                {"item_id": cart_item_ids[0], "user_id": user_id}
            ).fetchall()
        else:
            # Handle multiple items
            placeholders = ", ".join([f":id{i}" for i in range(len(cart_item_ids))])
            params = {"user_id": user_id}
            
            for i, item_id in enumerate(cart_item_ids):
                params[f"id{i}"] = item_id
                
            cart_query = f"""
                SELECT ci.*, pp.id as product_id, plp.list_price as price_per_unit 
                FROM cart_items ci
                JOIN product_product pp ON ci.product_id = pp.id
                JOIN product_template pt ON pp.template = pt.id
                JOIN product_list_price plp ON plp.template = pt.id
                WHERE ci.id IN ({placeholders}) 
                AND ci.patient_id = :user_id
                AND (ci.is_delet IS NULL OR ci.is_delet = false)
                AND (ci.order_pressed IS NULL OR ci.order_pressed = false)
            """
            cart_items = db.execute(text(cart_query), params).fetchall()
        
        if not cart_items:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No valid cart items found for the provided IDs"
            )
        
        # Calculate total amount
        total_amount = sum(item.price_per_unit * item.quantity for item in cart_items)
        
        # Create new order
        order_query = """
            INSERT INTO ecom_orders 
            (user_id, order_date, status, total_amount, payment_method, payment_status, shipping_address, notes)
            VALUES (:user_id, CURRENT_TIMESTAMP, 'pending', :total_amount, :payment_method, 'pending', :shipping_address, :notes)
            RETURNING id
        """
        
        order_result = db.execute(
            text(order_query),
            {
                "user_id": user_id,
                "total_amount": total_amount,
                "payment_method": order_data.payment_method,
                "shipping_address": order_data.shipping_address,
                "notes": order_data.notes
            }
        )
        order_id = order_result.scalar()
        
        # Create order items for each cart item
        for item in cart_items:
            item_total = item.price_per_unit * item.quantity
            
            order_item_query = """
                INSERT INTO ecom_order_items
                (order_id, product_id, quantity, price_per_unit, total_price, created_at, cart_id)
                VALUES (:order_id, :product_id, :quantity, :price_per_unit, :total_price, CURRENT_TIMESTAMP, :cart_id)
            """
            
            db.execute(
                text(order_item_query),
                {
                    "order_id": order_id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "price_per_unit": item.price_per_unit,
                    "total_price": item_total,
                    "cart_id": item.id
                }
            )
        
        # Mark cart items as processed (order_pressed = true)
        if len(cart_item_ids) == 1:
            update_cart_query = """
                UPDATE cart_items 
                SET order_pressed = true
                WHERE id = :item_id AND patient_id = :user_id
            """
            db.execute(
                text(update_cart_query), 
                {"item_id": cart_item_ids[0], "user_id": user_id}
            )
        else:
            # Handle multiple items with parameterized query
            placeholders = ", ".join([f":id{i}" for i in range(len(cart_item_ids))])
            params = {"user_id": user_id}
            
            for i, item_id in enumerate(cart_item_ids):
                params[f"id{i}"] = item_id
                
            update_cart_query = f"""
                UPDATE cart_items 
                SET order_pressed = true
                WHERE id IN ({placeholders}) AND patient_id = :user_id
            """
            db.execute(text(update_cart_query), params)
        
        # Commit the transaction
        db.commit()
        
        return {
            "order_id": order_id,
            "message": "Order created successfully"
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions (no need to rollback)
        raise
        
    except Exception as e:
        db.rollback()
        logger.error(f"Order creation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create order: {str(e)}"
        )
