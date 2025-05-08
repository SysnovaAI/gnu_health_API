from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from ..models.base import get_db, SECRET_KEY
from jose import jwt, JWTError
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cart-simple", tags=["Cart Simple"])

@router.get("/simple-cart")
def get_cart_items_simple(
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """A simplified cart endpoint that directly processes the JWT token"""
    
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        
    token = authorization.replace("Bearer ", "")
    
    try:
        # Decode token (no signature verification for testing)
        payload = jwt.decode(token, key="", options={"verify_signature": False})
        
        # Get user ID
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing user id")
        
        # Get user role
        role = payload.get("role", "").lower()
        logger.info(f"User role from token: '{role}'")
        
        # Get all cart items for the user
        cart_query = text("SELECT * FROM cart_items WHERE patient_id = :user_id AND is_delet = FALSE")
        cart_rows = db.execute(cart_query, {"user_id": user_id}).fetchall()
        
        cart_items = []
        total_items = 0
        total_amount = 0.0
        
        for cart_row in cart_rows:
            product_id = cart_row.product_id
            quantity = cart_row.quantity or 0
            
            # Get product info
            product_query = text("SELECT * FROM product_product WHERE id = :product_id")
            product = db.execute(product_query, {"product_id": product_id}).fetchone()
            if not product:
                continue
                
            template_id = product.template
            template_query = text("SELECT * FROM product_template WHERE id = :template_id")
            template = db.execute(template_query, {"template_id": template_id}).fetchone()
            if not template:
                continue
                
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
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") 