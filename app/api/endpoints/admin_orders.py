from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.api.models.base import get_db
from app.api.endpoints.appointments import get_current_user

router = APIRouter(prefix="/api/admin", tags=["Orders"])

# start


class OrderRequest(BaseModel):
    order_id: Optional[int] = None
    status: Optional[str] = None


@router.post("/orders/data")
def get_orders(
    request: OrderRequest,
    db: Session = Depends(get_db),
):
    """
    Retrieve either a specific order by ID or all orders (optionally filtered by status),
    including detailed product info for each item.
    """
    try:
        if request.order_id is not None:
            # Single order retrieval
            order_query = """
                SELECT id, user_id, order_date, status, total_amount
                FROM ecom_orders
                WHERE id = :order_id
            """
            order = db.execute(
                text(order_query), {"order_id": request.order_id}
            ).fetchone()

            if not order:
                raise HTTPException(status_code=404, detail="Order not found")

            items_query = """
                SELECT 
                    eoi.id, 
                    eoi.product_id, 
                    eoi.quantity, 
                    eoi.price_per_unit, 
                    eoi.total_price,
                    pt.name AS product_name,
                    pt.type AS product_type
                FROM ecom_order_items eoi
                JOIN product_product pp ON eoi.product_id = pp.id
                JOIN product_template pt ON pp.template = pt.id
                WHERE eoi.order_id = :order_id
            """
            items = db.execute(
                text(items_query), {"order_id": request.order_id}
            ).fetchall()

            return {
                "order_id": order.id,
                "user_id": order.user_id,
                "order_date": (
                    order.order_date.isoformat() if order.order_date else None
                ),
                "status": order.status,
                "total_amount": float(order.total_amount or 0.0),
                "items": [
                    {
                        "item_id": item.id,
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "product_type": item.product_type,
                        "quantity": item.quantity,
                        "price_per_unit": float(item.price_per_unit),
                        "total_price": float(item.total_price),
                    }
                    for item in items
                ],
            }

        # List of orders (optionally filtered by status)
        valid_statuses = {
            "pending",
            "processing",
            "ready_for_delivery",
            "completed",
            "cancelled",
        }
        query_params = {}
        orders_query = "SELECT * FROM ecom_orders"

        if request.status:
            if request.status not in valid_statuses:
                raise HTTPException(status_code=400, detail="Invalid status value")
            orders_query += " WHERE status = :status"
            query_params["status"] = request.status

        orders_query += " ORDER BY order_date DESC"
        orders = db.execute(text(orders_query), query_params).fetchall()

        result = []
        for order in orders:
            items_query = """
                SELECT 
                    eoi.id, 
                    eoi.product_id, 
                    eoi.quantity, 
                    eoi.price_per_unit, 
                    eoi.total_price,
                    pt.name AS product_name,
                    pt.type AS product_type
                FROM ecom_order_items eoi
                JOIN product_product pp ON eoi.product_id = pp.id
                JOIN product_template pt ON pp.template = pt.id
                WHERE eoi.order_id = :order_id
            """
            items = db.execute(text(items_query), {"order_id": order.id}).fetchall()

            result.append(
                {
                    "order_id": order.id,
                    "user_id": order.user_id,
                    "order_date": (
                        order.order_date.isoformat() if order.order_date else None
                    ),
                    "status": order.status,
                    "total_amount": float(order.total_amount or 0.0),
                    "items": [
                        {
                            "item_id": item.id,
                            "product_id": item.product_id,
                            "product_name": item.product_name,
                            "product_type": item.product_type,
                            "quantity": item.quantity,
                            "price_per_unit": float(item.price_per_unit),
                            "total_price": float(item.total_price),
                        }
                        for item in items
                    ],
                }
            )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching order data: {str(e)}"
        )


# Update order by status

# Allowed statuses
VALID_STATUSES = {
    "pending",
    "processing",
    "ready_for_delivery",
    "completed",
    "cancelled",
}


@router.put("/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    new_status: str = Body(..., embed=True, description="New status for the order"),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Update the status of a specific order.
    If status is set to 'completed', stock quantities are validated and deducted.
    """
    try:
        if new_status not in VALID_STATUSES:
            raise HTTPException(
                status_code=400, detail=f"Invalid status: '{new_status}'"
            )

        order_row = db.execute(
            text("SELECT status FROM ecom_orders WHERE id = :order_id"),
            {"order_id": order_id},
        ).fetchone()

        if not order_row:
            raise HTTPException(status_code=404, detail="Order not found")

        if order_row.status == "completed":
            raise HTTPException(
                status_code=400,
                detail="Cannot change status. Order is already 'completed'.",
            )

        # Fetch order items
        items = db.execute(
            text(
                """
                SELECT eoi.product_id, eoi.quantity
                FROM ecom_order_items eoi
                WHERE eoi.order_id = :order_id
            """
            ),
            {"order_id": order_id},
        ).fetchall()

        # --- Stock Check Before Update ---
        if new_status == "completed":
            for item in items:
                product_id = item.product_id
                quantity_needed = item.quantity

                stock_lot_row = db.execute(
                    text(
                        "SELECT id, number FROM public.stock_lot WHERE product = :product_id"
                    ),
                    {"product_id": product_id},
                ).fetchone()

                if (
                    not stock_lot_row
                    or float(stock_lot_row.number or 0) < quantity_needed
                ):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient stock for product ID {product_id}. Required: {quantity_needed}, Available: {stock_lot_row.number if stock_lot_row else 0}",
                    )

        # --- Update Order Status ---
        db.execute(
            text("UPDATE ecom_orders SET status = :new_status WHERE id = :order_id"),
            {"new_status": new_status, "order_id": order_id},
        )

        # --- Deduct Stock ---
        if new_status == "completed":
            for item in items:
                product_id = item.product_id
                quantity = item.quantity

                stock_lot_row = db.execute(
                    text(
                        "SELECT id, number FROM public.stock_lot WHERE product = :product_id"
                    ),
                    {"product_id": product_id},
                ).fetchone()

                current_number = float(stock_lot_row.number or 0)
                new_number = current_number - quantity

                db.execute(
                    text(
                        """
                        UPDATE public.stock_lot
                        SET number = :number, write_date = NOW()
                        WHERE id = :id
                    """
                    ),
                    {"number": new_number, "id": stock_lot_row.id},
                )

        db.commit()

        return {
            "message": "Order status updated successfully",
            "order_id": order_id,
            "new_status": new_status,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error updating order status: {str(e)}"
        )


# end
