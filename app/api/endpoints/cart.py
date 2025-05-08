from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from pydantic import BaseModel
from ..models.base import get_db, SECRET_KEY
from jose import jwt, JWTError
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cart", tags=["Cart"])

class AddCartItemRequest(BaseModel):
    product_id: int
    quantity: int

class UpdateCartItemRequest(BaseModel):
    quantity: int

# New direct cart access endpoint - alternative implementation
@router.get("/direct", include_in_schema=False)
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
            # Add condition to exclude items where order_pressed is TRUE
            cart_query = text("SELECT * FROM cart_items WHERE patient_id = :user_id AND is_delet = FALSE AND order_pressed = FALSE")
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

# 1. Get all cart items endpoint
@router.get("/", include_in_schema=False)
def get_cart_items(
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
            # Add condition to exclude items where order_pressed is TRUE
            cart_query = text("SELECT * FROM cart_items WHERE patient_id = :user_id AND is_delet = FALSE AND order_pressed = FALSE")
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

# 2. Add to cart endpoint
@router.post("/add")
def add_cart_item(
    item: AddCartItemRequest,
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
            
            # Insert into cart_items with patient_id as res_user.id
            try:
                insert_query = text("""
                    INSERT INTO cart_items (
                        patient_id, product_id, quantity, created_at, updated_at, is_delet, order_pressed
                    ) VALUES (
                        :patient_id, :product_id, :quantity, NOW(), NOW(), :is_delet, :order_pressed
                    )
                    RETURNING id;
                """)
                result = db.execute(insert_query, {
                    "patient_id": user_id,  # Use res_user.id
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "is_delet": False,
                    "order_pressed": False
                }).fetchone()
                db.commit()
                return {"success": True, "cart_item_id": result.id}
            except Exception as e:
                db.rollback()
                raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
            
        except JWTError as e:
            logger.error(f"JWT error: {str(e)}")
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(e), "trace": traceback.format_exc()}

# 3. Update cart item endpoint
@router.put("/item/{item_id}", include_in_schema=False)
def update_cart_item(
    item_id: int,
    item_update: UpdateCartItemRequest,
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
            
            # Check if the cart item belongs to the user
            check_query = text("SELECT * FROM cart_items WHERE id = :item_id AND patient_id = :user_id AND is_delet = FALSE")
            cart_item = db.execute(check_query, {"item_id": item_id, "user_id": user_id}).fetchone()
            
            if not cart_item:
                # Log the error for debugging
                logger.error(f"Cart item {item_id} not found or not owned by user {user_id}")
                # Raising an HTTPException here will be properly propagated
                raise HTTPException(status_code=404, detail="Cart item not found or not owned by this user")
            
            # Update the quantity
            update_query = text("""
                UPDATE cart_items
                SET quantity = :quantity, updated_at = NOW()
                WHERE id = :item_id AND patient_id = :user_id
                RETURNING id
            """)
            
            result = db.execute(update_query, {
                "item_id": item_id, 
                "user_id": user_id,
                "quantity": item_update.quantity
            }).fetchone()
            db.commit()
            print(f"result: {result}")
            if result:
                return {"success": True, "message": "Cart item quantity updated"}
            else:
                # This is a more serious error that should be a 500
                raise HTTPException(status_code=500, detail="Failed to update cart item")
            
        except JWTError as e:
            logger.error(f"JWT error: {str(e)}")
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
        
        # Important: Don't catch HTTPException here, let it propagate    
        except Exception as e:
            if isinstance(e, HTTPException):
                raise  # Re-raise HTTPException so it's properly handled by FastAPI
            logger.error(f"Unexpected error: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))
            
    except HTTPException as http_exc:
        # Re-raise HTTPException to ensure correct status code is returned
        raise http_exc
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

# 4. Delete/remove cart item endpoint
@router.delete("/item/{item_id}", include_in_schema=False)
def delete_cart_item(
    item_id: int,
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
            
            # Check if the cart item belongs to the user
            check_query = text("SELECT * FROM cart_items WHERE id = :item_id AND patient_id = :user_id")
            cart_item = db.execute(check_query, {"item_id": item_id, "user_id": user_id}).fetchone()
            
            if not cart_item:
                raise HTTPException(status_code=404, detail="Cart item not found or not owned by this user")
            
            # We'll do a soft delete by setting is_delet to TRUE
            update_query = text("""
                UPDATE cart_items
                SET is_delet = TRUE, updated_at = NOW()
                WHERE id = :item_id AND patient_id = :user_id
                RETURNING id
            """)
            
            result = db.execute(update_query, {"item_id": item_id, "user_id": user_id}).fetchone()
            db.commit()
            
            if result:
                return {"success": True, "message": "Item removed from cart"}
            else:
                raise HTTPException(status_code=500, detail="Failed to remove item from cart")
            
        except JWTError as e:
            logger.error(f"JWT error: {str(e)}")
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(e), "trace": traceback.format_exc()}

# New POST endpoint for getting cart items (workaround for GET issues)
@router.post("/items")
def get_cart_items_post(
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Retrieve cart items using POST instead of GET as a workaround for the middleware issues.
    This endpoint performs the same function as the original GET /api/cart endpoint.
    """
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
            # Add condition to exclude items where order_pressed is TRUE
            cart_query = text("SELECT * FROM cart_items WHERE patient_id = :user_id AND is_delet = FALSE AND order_pressed = FALSE")
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

# Add a new endpoint for updating cart items by product_id
@router.put("/product/{product_id}")
def update_cart_item_by_product(
    product_id: int,
    item_update: UpdateCartItemRequest,
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
            
            # Find the cart item by product_id instead of item_id
            check_query = text("SELECT * FROM cart_items WHERE product_id = :product_id AND patient_id = :user_id AND is_delet = FALSE")
            cart_item = db.execute(check_query, {"product_id": product_id, "user_id": user_id}).fetchone()
            
            if not cart_item:
                # Log the error for debugging
                logger.error(f"Cart item with product_id {product_id} not found or not owned by user {user_id}")
                # Raising an HTTPException here will be properly propagated
                raise HTTPException(status_code=404, detail="Product not found in user's cart")
            
            # Get the cart item id
            cart_item_id = cart_item.id
            
            # Update the quantity
            update_query = text("""
                UPDATE cart_items
                SET quantity = :quantity, updated_at = NOW()
                WHERE id = :cart_item_id AND patient_id = :user_id
                RETURNING id
            """)
            
            result = db.execute(update_query, {
                "cart_item_id": cart_item_id, 
                "user_id": user_id,
                "quantity": item_update.quantity
            }).fetchone()
            db.commit()
            
            if result:
                return {"success": True, "message": f"Cart item for product {product_id} quantity updated"}
            else:
                # This is a more serious error that should be a 500
                raise HTTPException(status_code=500, detail="Failed to update cart item")
            
        except JWTError as e:
            logger.error(f"JWT error: {str(e)}")
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
        
        # Important: Don't catch HTTPException here, let it propagate    
        except Exception as e:
            if isinstance(e, HTTPException):
                raise  # Re-raise HTTPException so it's properly handled by FastAPI
            logger.error(f"Unexpected error: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))
            
    except HTTPException as http_exc:
        # Re-raise HTTPException to ensure correct status code is returned
        raise http_exc
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

# Add a new endpoint for deleting cart items by product_id
@router.delete("/delete/product/{product_id}")
def delete_cart_item_by_product(
    product_id: int,
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
            
            # Find the cart item by product_id
            check_query = text("SELECT * FROM cart_items WHERE product_id = :product_id AND patient_id = :user_id AND is_delet = FALSE")
            cart_item = db.execute(check_query, {"product_id": product_id, "user_id": user_id}).fetchone()
            
            if not cart_item:
                # Log the error for debugging
                logger.error(f"Cart item with product_id {product_id} not found or not owned by user {user_id}")
                # Raising an HTTPException here will be properly propagated
                raise HTTPException(status_code=404, detail="Product not found in user's cart")
            
            # Get the cart item id
            cart_item_id = cart_item.id
            
            # We'll do a soft delete by setting is_delet to TRUE
            update_query = text("""
                UPDATE cart_items
                SET is_delet = TRUE, updated_at = NOW()
                WHERE id = :cart_item_id AND patient_id = :user_id
                RETURNING id
            """)
            
            result = db.execute(update_query, {"cart_item_id": cart_item_id, "user_id": user_id}).fetchone()
            db.commit()
            
            if result:
                return {"success": True, "message": f"Item with product ID {product_id} removed from cart"}
            else:
                raise HTTPException(status_code=500, detail="Failed to remove item from cart")
            
        except JWTError as e:
            logger.error(f"JWT error: {str(e)}")
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
        
        # Important: Don't catch HTTPException here, let it propagate    
        except Exception as e:
            if isinstance(e, HTTPException):
                raise  # Re-raise HTTPException so it's properly handled by FastAPI
            logger.error(f"Unexpected error: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))
            
    except HTTPException as http_exc:
        # Re-raise HTTPException to ensure correct status code is returned
        raise http_exc
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
