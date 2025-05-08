from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from typing import Optional, List
from datetime import datetime
from app.api.models.base import get_db
from app.api.endpoints.appointments import get_current_user

router = APIRouter(prefix="/api/admin", tags=["Admin - Model Access"])


# Pydantic Schemas
class ModelAccessCreate(BaseModel):
    model_id: int  # Required
    group_id: int  # Required
    description: Optional[str] = None
    perm_read: bool = False
    perm_write: bool = False
    perm_create: bool = False
    perm_delete: bool = False
    active: bool = False


class ModelAccessUpdate(ModelAccessCreate):
    pass


# Create Access Rule
@router.post("/access")
async def create_access_rule(
    data: ModelAccessCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        # Step 1: Check if the user is part of the 'Administration' group
        is_admin_query = text(
            """
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name LIKE '%Administration%' AND ugr."user" = :user_id
            LIMIT 1
        """
        )
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()

        # If the user is not part of the 'Administration' group, deny access
        if not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Not part of Administration group.",
            )

        # Step 2: Check if the access rule already exists for the given model_id and group_id
        existing_rule_query = text(
            """
            SELECT 1
            FROM ir_model_access
            WHERE model = :model_id AND "group" = :group_id
            LIMIT 1
        """
        )
        existing_rule = db.execute(
            existing_rule_query, {"model_id": data.model_id, "group_id": data.group_id}
        ).first()

        # If the access rule already exists, deny insertion
        if existing_rule:
            raise HTTPException(
                status_code=400,
                detail="Access rule already exists for this model and group.",
            )

        # Step 3: Proceed with creating the access rule
        insert = text(
            """
            INSERT INTO ir_model_access (
                model, "group", description, perm_read, perm_write, perm_create, perm_delete,
                active, create_date, create_uid, write_date, write_uid
            )
            VALUES (
                :model, :group, :description, :perm_read, :perm_write, :perm_create, :perm_delete,
                :active, :create_date, :uid, :write_date, :uid
            ) RETURNING id
        """
        )
        result = db.execute(
            insert,
            {
                "model": data.model_id,
                "group": data.group_id,
                "description": data.description,
                "perm_read": data.perm_read,
                "perm_write": data.perm_write,
                "perm_create": data.perm_create,
                "perm_delete": data.perm_delete,
                "active": data.active,
                "create_date": datetime.now(),
                "write_date": datetime.now(),
                "uid": user["id"],
            },
        )
        db.commit()
        return {"success": True, "access_id": result.fetchone()[0]}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error creating access rule: {str(e)}"
        )


# List All Access Rules
@router.get("/access")
async def list_all_access(
    db: Session = Depends(get_db), user: dict = Depends(get_current_user)
):
    try:
        # Step 1: Check if the user is part of the 'Administration' group
        is_admin_query = text(
            """
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name LIKE '%Administration%' AND ugr."user" = :user_id
            LIMIT 1
        """
        )
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()

        # If the user is not part of the 'Administration' group, deny access
        if not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Not part of Administration group.",
            )

        # Step 2: Fetch all access rules
        query = text(
            """
            SELECT a.id, a.description, a.perm_read, a.perm_write, a.perm_create, a.perm_delete,
                   a.active, m.model AS model_name, g.name AS group_name
            FROM ir_model_access a
            JOIN ir_model m ON m.id = a.model
            JOIN res_group g ON g.id = a.group
            ORDER BY a.id DESC
        """
        )
        result = db.execute(query).fetchall()

        access_list = [
            {
                "id": r[0],
                "description": r[1],
                "perm_read": r[2],
                "perm_write": r[3],
                "perm_create": r[4],
                "perm_delete": r[5],
                "active": r[6],
                "model": r[7],
                "group": r[8],
            }
            for r in result
        ]

        return {"success": True, "access_rules": access_list}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching access rules: {str(e)}"
        )


# Get Access  by id
@router.get("/access/{access_id}")
async def get_access_by_id(
    access_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Get a specific model access rule by access_id, including model and group names.
    This will only be accessible if the current user is part of the 'Administration' group.
    """
    try:
        # Step 1: Check if the user is part of the 'Administration' group
        is_admin_query = text(
            """
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name LIKE '%Administration%' AND ugr."user" = :user_id
            LIMIT 1
        """
        )
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()

        # If the user is not part of the 'Administration' group, deny access
        if not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Not part of Administration group.",
            )

        # Step 2: Fetch the specific access rule by access_id
        query = text(
            """
            SELECT a.id, a.description, a.perm_read, a.perm_write, a.perm_create, a.perm_delete,
                   a.active, m.model AS model_name, g.name AS group_name
            FROM ir_model_access a
            JOIN ir_model m ON m.id = a.model
            JOIN res_group g ON g.id = a.group
            WHERE a.id = :access_id
        """
        )
        result = db.execute(query, {"access_id": access_id}).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Access rule not found")

        rule = {
            "id": result[0],
            "description": result[1],
            "perm_read": result[2],
            "perm_write": result[3],
            "perm_create": result[4],
            "perm_delete": result[5],
            "active": result[6],
            "model": result[7],
            "group": result[8],
        }
        return {"success": True, "access_rule": rule}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving access rule: {str(e)}"
        )


# Get Access Rules by Group
@router.get("/access/group/{group_id}")
async def get_access_by_group(
    group_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)
):
    """
    Get model access rules by group ID.
    This will only be accessible if the current user is part of the 'Administration' group.
    """
    try:
        # Step 1: Check if the user is part of the 'Administration' group
        is_admin_query = text(
            """
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name LIKE '%Administration%' AND ugr."user" = :user_id
            LIMIT 1
        """
        )
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()

        # If the user is not part of the 'Administration' group, deny access
        if not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Not part of Administration group.",
            )

        # Step 2: Fetch the access rules for the given group_id
        query = text(
            """
            SELECT a.id, a.description, a.perm_read, a.perm_write, a.perm_create, a.perm_delete,
                   a.active, m.name AS model_name
            FROM ir_model_access a
            JOIN ir_model m ON m.id = a.model
            WHERE a.group = :group_id
            ORDER BY m.model
        """
        )
        result = db.execute(query, {"group_id": group_id}).fetchall()

        rules = [
            {
                "id": r[0],
                "description": r[1],
                "perm_read": r[2],
                "perm_write": r[3],
                "perm_create": r[4],
                "perm_delete": r[5],
                "active": r[6],
                "model": r[7],
            }
            for r in result
        ]

        return {"success": True, "group_id": group_id, "access_rules": rules}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving group access: {str(e)}"
        )


class ModelAccessUpdate(BaseModel):
    id: int
    model_id: Optional[int] = None
    group_id: Optional[int] = None
    description: Optional[str] = None
    perm_read: Optional[bool] = None
    perm_write: Optional[bool] = None
    perm_create: Optional[bool] = None
    perm_delete: Optional[bool] = None
    active: Optional[bool] = None


@router.put("/access")
async def update_multiple_access_rules(
    data: List[ModelAccessUpdate],
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Batch update access rules in ir_model_access.
    This will only be accessible if the current user is part of the 'Administration' group.
    """
    try:
        # Step 1: Check if the user is part of the 'Administration' group
        is_admin_query = text(
            """
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name LIKE '%Administration%' AND ugr."user" = :user_id
            LIMIT 1
        """
        )
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()

        # If the user is not part of the 'Administration' group, deny access
        if not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Not part of Administration group.",
            )

        # Step 2: Loop through the data and perform updates
        for item in data:
            # Check if access rule exists
            check = db.execute(
                text("SELECT id FROM ir_model_access WHERE id = :id"), {"id": item.id}
            ).fetchone()
            if not check:
                raise HTTPException(
                    status_code=404, detail=f"Access rule with ID {item.id} not found"
                )

            current = db.execute(
                text(
                    """
                    SELECT model, "group", description, perm_read, perm_write, 
                           perm_create, perm_delete, active 
                    FROM ir_model_access WHERE id = :id
                """
                ),
                {"id": item.id},
            ).fetchone()

            update_data = {
                "id": item.id,
                "model": item.model_id if item.model_id is not None else current[0],
                "group": item.group_id if item.group_id is not None else current[1],
                "description": (
                    item.description if item.description is not None else current[2]
                ),
                "perm_read": (
                    item.perm_read if item.perm_read is not None else current[3]
                ),
                "perm_write": (
                    item.perm_write if item.perm_write is not None else current[4]
                ),
                "perm_create": (
                    item.perm_create if item.perm_create is not None else current[5]
                ),
                "perm_delete": (
                    item.perm_delete if item.perm_delete is not None else current[6]
                ),
                "active": item.active if item.active is not None else current[7],
                "write_date": datetime.now(),
                "uid": user["id"],
            }

            update_query = text(
                """
                UPDATE ir_model_access SET
                    model = :model,
                    "group" = :group,
                    description = :description,
                    perm_read = :perm_read,
                    perm_write = :perm_write,
                    perm_create = :perm_create,
                    perm_delete = :perm_delete,
                    active = :active,
                    write_date = :write_date,
                    write_uid = :uid
                WHERE id = :id
            """
            )
            db.execute(update_query, update_data)

        db.commit()
        return {"success": True, "message": "Access rules updated successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error updating access rules: {str(e)}"
        )


# Delete Access Rule
@router.delete("/access/{access_id}")
async def delete_access_rule(
    access_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Soft delete an access rule by setting active = FALSE.
    This will only be accessible if the current user is part of the 'Administration' group.
    """
    try:
        # Step 1: Check if the user is part of the 'Administration' group
        is_admin_query = text(
            """
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name LIKE '%Administration%' AND ugr."user" = :user_id
            LIMIT 1
        """
        )
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()

        # If the user is not part of the 'Administration' group, deny access
        if not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Not part of Administration group.",
            )

        # Step 2: Check if the access rule exists
        check = db.execute(
            text("SELECT id FROM ir_model_access WHERE id = :id"), {"id": access_id}
        ).fetchone()
        if not check:
            raise HTTPException(status_code=404, detail="Access rule not found")

        # Step 3: Soft delete (deactivate) the access rule
        soft_delete_query = text(
            """
            UPDATE ir_model_access
            SET active = FALSE,
                write_date = :write_date,
                write_uid = :uid
            WHERE id = :id
        """
        )
        db.execute(
            soft_delete_query,
            {"id": access_id, "write_date": datetime.now(), "uid": user["id"]},
        )
        db.commit()

        return {"success": True, "message": "Access rule deactivated (soft deleted)"}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error soft deleting access rule: {str(e)}"
        )
