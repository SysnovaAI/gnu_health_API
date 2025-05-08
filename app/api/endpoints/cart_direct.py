from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from ..models.base import get_db, SECRET_KEY
from jose import jwt, JWTError
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cart-direct", tags=["Direct Cart Access"])

@router.get("/cart-direct")
def get_cart_items_direct(
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    try:
        # Log the token received
        logger.info(f"Authorization header: {authorization}")
        
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
            
        token = authorization.replace("Bearer ", "")
        
        # Manually decode the JWT
        try:
            # Use the SECRET_KEY from your base.py
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            logger.info(f"Decoded payload: {payload}")
            
            # Get the user ID from the payload
            user_id = payload.get("id")
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid token: missing user id")
            
            # Log the role but don't check it
            role = payload.get("role")
            logger.info(f"User role from token: '{role}' - skipping role check")
                
            logger.info(f"Using user_id: {user_id}")
            
            # Get all cart items for the user (use lowercase table name)
            cart_query = text("SELECT * FROM cart_items WHERE patient_id = :user_id AND is_delet = FALSE")
            cart_rows = db.execute(cart_query, {"user_id": user_id}).fetchall()
            
            cart_items = []
            total_items = 0
            total_amount = 0.0
            
            for cart_row in cart_rows:
                product_id = cart_row.product_id
                quantity = cart_row.quantity or 0
                # Get product_product row
                product_query = text("SELECT * FROM product_product WHERE id = :product_id")
                product = db.execute(product_query, {"product_id": product_id}).fetchone()
                if not product:
                    continue  # skip if product not found
                template_id = product.template
                # Get product_template row
                template_query = text("SELECT * FROM product_template WHERE id = :template_id")
                template = db.execute(template_query, {"template_id": template_id}).fetchone()
                if not template:
                    continue  # skip if template not found
                # Get product_list_price row
                price_query = text("SELECT * FROM product_list_price WHERE template = :template_id")
                price_row = db.execute(price_query, {"template_id": template_id}).fetchone()
                unit_price = float(price_row.list_price) if price_row and price_row.list_price is not None else 0.0
                subtotal = unit_price * quantity
                cart_items.append({
                    "id": cart_row.id,
                    "product_id": product_id,
                    "product_name": template.name,
                    "type": template.type,
                    "unit_price": unit_price,
                    "quantity": quantity,
                    "subtotal": round(subtotal, 2)
                })
                total_items += quantity
                total_amount += subtotal
            
            return {
                "cart_items": cart_items,
                "total_items": total_items,
                "total_amount": round(total_amount, 2)
            }
            
        except JWTError as e:
            logger.error(f"JWT error: {str(e)}")
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(e), "trace": traceback.format_exc()} 