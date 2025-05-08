from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from app.api.models.base import get_db
from app.api.endpoints.appointments import get_current_user  # reuse your existing auth dependency

router = APIRouter(prefix="/api/admin", tags=["Admin - Groups/Roles"])

# get group list
class GroupCreateRequest(BaseModel):
    name: str
    parent: int | None = None
    active: bool = True

@router.get("/groups")
def get_groups(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """
    Fetch groups:
    - If user is 'Administration', fetch all active groups.
    - Otherwise, fetch user's roles with 'Administration' in the name and their child roles.
    """
    try:
        # Step 1: Check if user is part of 'Administration' group
        admin_check_query = text("""
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE ugr."user" = :user_id
            AND g.name = 'Administration'
            LIMIT 1
        """)
        admin_result = db.execute(admin_check_query, {"user_id": user["id"]}).first()

        if admin_result:
            # User is an Administration member, fetch ALL active groups
            query = text("""
                SELECT id, name, active, create_date, parent
                FROM res_group
                WHERE active = TRUE
                ORDER BY name
            """)
            result = db.execute(query).fetchall()

        else:
            # Step 2: Fetch roles related to 'Administration' in the name
            role_query = text("""
                SELECT g.id, g.name
                FROM res_group g
                JOIN "res_user-res_group" ugr ON ugr."group" = g.id
                WHERE ugr."user" = :user_id
                AND g.name ILIKE '%Administration%'
            """)
            roles = db.execute(role_query, {"user_id": user["id"]}).fetchall()

            if not roles:
                raise HTTPException(status_code=403, detail="Access denied. No Administration-related role found.")

            # Step 3: Find child groups based on role IDs
            role_ids = [r[0] for r in roles]  # collect role IDs

            if role_ids:
                role_ids_placeholders = ", ".join([str(rid) for rid in role_ids])  # create placeholders for IN clause
                group_query = text(f"""
                    SELECT id, name, active, create_date, parent
                    FROM res_group
                    WHERE active = TRUE
                    AND (id IN ({role_ids_placeholders}) OR parent IN ({role_ids_placeholders}))
                    ORDER BY name
                """)
                result = db.execute(group_query).fetchall()
            else:
                # If no roles, return an empty list or raise an error
                result = []

        # Step 4: Build response
        groups = []
        for row in result:
            groups.append({
                "id": row[0],
                "name": row[1],
                "active": row[2],
                "create_date": str(row[3]) if row[3] else None,
                "parent": row[4]
            })
        
        return {"success": True, "groups": groups}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# create user group
@router.post("/groups")
async def create_group(
    group: GroupCreateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Create a new group (res_group). Only users in the 'Administration' group can create new groups.
    """
    try:
        # Check if the user is part of the 'Administration' group
        admin_check_query = text("""
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE ugr."user" = :user_id
            AND g.name = 'Administration'
            LIMIT 1
        """)
        admin_result = db.execute(admin_check_query, {"user_id": user["id"]}).first()

        if not admin_result:
            raise HTTPException(status_code=403, detail="Access denied. Only 'Administration' users can create groups.")

        # Check if the group name already exists
        check_query = text("SELECT id FROM res_group WHERE name = :name")
        existing = db.execute(check_query, {"name": group.name}).fetchone()

        if existing:
            raise HTTPException(status_code=400, detail="Group name already exists")

        # Insert new group into the database
        insert_query = text("""
            INSERT INTO res_group (name, active, create_date, create_uid, write_date, write_uid, parent)
            VALUES (:name, :active, :create_date, :uid, :write_date, :uid, :parent)
            RETURNING id, name, active, create_date, parent
        """)
        result = db.execute(insert_query, {
            "name": group.name,
            "active": group.active,
            "create_date": datetime.now(),
            "write_date": datetime.now(),
            "uid": user["id"],
            "parent": group.parent
        })
        db.commit()
        
        # Fetch the newly created group data
        new_group = result.fetchone()

        # Return the newly created group details
        return {
            "success": True,
            "message": "Group created successfully",
            "group": {
                "id": new_group[0],
                "name": new_group[1],
                "active": new_group[2],
                "create_date": str(new_group[3]),  # Convert datetime to string
                "parent": new_group[4]
            }
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating group: {str(e)}")


# get group list by id
@router.get("/groups/{group_id}")
async def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Retrieve a specific group by ID from res_group.
    Users in the 'Administration' group can access any group.
    Users in child groups can only access their own child groups.
    """
    try:
        # Step 1: Check if user is part of 'Administration' group
        is_admin_query = text("""
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name = 'Administration' AND ugr."user" = :user_id
            LIMIT 1
        """)
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()

        if is_admin:
            # User is in the 'Administration' group, allow access to any group
            group_query = text("""
                SELECT id, name, active, create_date, parent
                FROM res_group
                WHERE id = :group_id
            """)
            group = db.execute(group_query, {"group_id": group_id}).fetchone()

            if not group:
                raise HTTPException(status_code=404, detail="Group not found.")
            
            return {
                "success": True,
                "group": {
                    "id": group.id,
                    "name": group.name,
                    "active": group.active,
                    "create_date": str(group.create_date),
                    "parent": group.parent
                }
            }

        # Step 2: Check if the user is part of a child group and if the requested group is a child of theirs
        child_groups_query = text("""
            SELECT g2.id
            FROM res_group g1
            JOIN res_group g2 ON g2.parent = g1.id
            JOIN "res_user-res_group" ugr ON ugr."group" = g1.id
            WHERE ugr."user" = :user_id
        """)
        child_groups = db.execute(child_groups_query, {"user_id": user["id"]}).fetchall()
        child_group_ids = [c[0] for c in child_groups]

        # If group_id is not a child group of the user, deny access
        if group_id not in child_group_ids:
            raise HTTPException(status_code=403, detail="Access denied. You can only access your child groups.")

        # Step 3: Fetch the group data
        group_query = text("""
            SELECT id, name, active, create_date, parent
            FROM res_group
            WHERE id = :group_id
        """)
        group = db.execute(group_query, {"group_id": group_id}).fetchone()

        if not group:
            raise HTTPException(status_code=404, detail="Group not found.")

        return {
            "success": True,
            "group": {
                "id": group.id,
                "name": group.name,
                "active": group.active,
                "create_date": str(group.create_date),
                "parent": group.parent
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving group: {str(e)}")

# update a group by id
class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None
    parent: Optional[int] = None

@router.put("/groups/{group_id}")
async def update_group(
    group_id: int,
    update: GroupUpdateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    try:
        # Step 1: Check if user is part of Administration
        is_admin_query = text("""
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name = 'Administration' AND ugr."user" = :user_id
            LIMIT 1
        """)
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()

        if not is_admin:
            raise HTTPException(status_code=403, detail="Access denied. Not part of Administration group.")

        # Step 2: Check if user is Direct Administration
        is_direct_admin_query = text("""
            SELECT 1
            FROM "res_user-res_group"
            WHERE "user" = :user_id
            AND "group" = (SELECT id FROM res_group WHERE name = 'Administration' LIMIT 1)
            LIMIT 1
        """)
        is_direct_admin = db.execute(is_direct_admin_query, {"user_id": user["id"]}).first()

        # Step 3: Fetch group to be updated
        group_query = text("""
            SELECT id, name, active, parent, create_date
            FROM res_group
            WHERE id = :group_id
        """)
        group = db.execute(group_query, {"group_id": group_id}).fetchone()

        if not group:
            raise HTTPException(status_code=404, detail="Group not found.")

        if is_direct_admin:
            # ✅ Super Admin: Can update name, active, parent (any field)

            if update.name:
                # Check if name already exists
                name_check_query = text("""
                    SELECT id FROM res_group
                    WHERE name = :name 
                """)
                name_exists = db.execute(name_check_query, {"name": update.name}).first()

                if name_exists:
                    raise HTTPException(status_code=400, detail="Group name already exists.")

            # Prepare dynamic update fields
            update_fields = []
            params = {"group_id": group_id, "uid": user["id"], "write_date": datetime.now()}
            
            if update.name is not None:
                update_fields.append("name = :name")
                params["name"] = update.name
            if update.active is not None:
                update_fields.append("active = :active")
                params["active"] = update.active
            if update.parent is not None:
                update_fields.append("parent = :parent")
                params["parent"] = update.parent

            if update_fields:
                update_query = text(f"""
                    UPDATE res_group
                    SET {', '.join(update_fields)},
                        write_date = :write_date,
                        write_uid = :uid
                    WHERE id = :group_id
                """)
                db.execute(update_query, params)
                db.commit()

        else:
            # ✅ Part of Admin: can only update 'active' field

            # Fetch user's child groups
            child_groups_query = text("""
                SELECT g2.id
                FROM res_group g1
                JOIN res_group g2 ON g2.parent = g1.id
                JOIN "res_user-res_group" ugr ON ugr."group" = g1.id
                WHERE ugr."user" = :user_id
            """)
            child_groups = db.execute(child_groups_query, {"user_id": user["id"]}).fetchall()
            child_group_ids = [c[0] for c in child_groups]

            if group_id not in child_group_ids:
                raise HTTPException(status_code=403, detail="Access denied. You can only update your child groups.")

            if update.active is None:
                raise HTTPException(status_code=400, detail="Only 'active' field can be updated.")

            update_query = text("""
                UPDATE res_group
                SET active = :active,
                    write_date = :write_date,
                    write_uid = :uid
                WHERE id = :group_id
            """)
            db.execute(update_query, {
                "active": update.active,
                "write_date": datetime.now(),
                "uid": user["id"],
                "group_id": group_id
            })
            db.commit()

        # Step 4: Return updated group
        updated_group_query = text("""
            SELECT id, name, active, create_date, parent
            FROM res_group
            WHERE id = :group_id
        """)
        updated_group = db.execute(updated_group_query, {"group_id": group_id}).fetchone()

        return {
            "success": True,
            "group": {
                "id": updated_group.id,
                "name": updated_group.name,
                "active": updated_group.active,
                "create_date": str(updated_group.create_date),
                "parent": updated_group.parent
            }
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating group: {str(e)}")

# soft delete a group by id
@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Soft delete a group by setting active = FALSE
    """
    try:
        # Step 1: Check if user is part of Administration
        is_admin_query = text("""
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name = 'Administration' AND ugr."user" = :user_id
            LIMIT 1
        """)
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()

        if not is_admin:
            raise HTTPException(status_code=403, detail="Access denied. Not part of Administration group.")

        # Step 2: Check if user is Direct Administration
        is_direct_admin_query = text("""
            SELECT 1
            FROM "res_user-res_group"
            WHERE "user" = :user_id
            AND "group" = (SELECT id FROM res_group WHERE name = 'Administration' LIMIT 1)
            LIMIT 1
        """)
        is_direct_admin = db.execute(is_direct_admin_query, {"user_id": user["id"]}).first()

        # Step 3: Fetch the group to be deleted
        check_query = text("""
            SELECT id, parent
            FROM res_group
            WHERE id = :group_id
        """)
        group = db.execute(check_query, {"group_id": group_id}).fetchone()

        if not group:
            raise HTTPException(status_code=404, detail="Group not found.")

        if is_direct_admin:
            # ✅ Super Admin: can delete any group
            pass
        else:
            # ✅ Normal Admin: can delete only child groups
            child_groups_query = text("""
                SELECT g2.id
                FROM res_group g1
                JOIN res_group g2 ON g2.parent = g1.id
                JOIN "res_user-res_group" ugr ON ugr."group" = g1.id
                WHERE ugr."user" = :user_id
            """)
            child_groups = db.execute(child_groups_query, {"user_id": user["id"]}).fetchall()
            child_group_ids = [c[0] for c in child_groups]

            if group_id not in child_group_ids:
                raise HTTPException(status_code=403, detail="Access denied. You can only delete your child groups.")

        # Step 4: Soft delete (set active = False)
        delete_query = text("""
            UPDATE res_group
            SET active = FALSE,
                write_date = :write_date,
                write_uid = :uid
            WHERE id = :group_id
        """)
        db.execute(delete_query, {
            "write_date": datetime.now(),
            "uid": user["id"],
            "group_id": group_id
        })
        db.commit()

        return {"success": True, "message": "Group deleted (deactivated) successfully."}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting group: {str(e)}")

# add users to group
class AddUsersToGroupRequest(BaseModel):
    user_ids: list[int]

@router.post("/groups/{group_id}/add-users")
async def add_users_to_group(
    group_id: int,
    data: AddUsersToGroupRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    try:
        now = datetime.now()

        # Step 1: Check if user is part of 'Administration'
        is_admin_query = text("""
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name LIKE '%Administration%' AND ugr."user" = :user_id
            LIMIT 1
        """)
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()

        if not is_admin:
            raise HTTPException(status_code=403, detail="Access denied. Not part of Administration group.")

        # Step 2: Check if user is Direct Administration
        is_direct_admin_query = text("""
            SELECT 1
            FROM "res_user-res_group"
            WHERE "user" = :user_id
            AND "group" = (SELECT id FROM res_group WHERE name = 'Administration' LIMIT 1)
            LIMIT 1
        """)
        is_direct_admin = db.execute(is_direct_admin_query, {"user_id": user["id"]}).first()

        # Step 3: Fetch group to be updated
        group_query = text("""
            SELECT id, name, active, parent, create_date
            FROM res_group
            WHERE id = :group_id
        """)
        group = db.execute(group_query, {"group_id": group_id}).fetchone()

        if not group:
            raise HTTPException(status_code=404, detail="Group not found.")

        if is_direct_admin:
            # ✅ Super Admin: Can add users to any group
            groups_to_check = [group_id]
        else:
            # ✅ Part of Admin: can only add users to their child groups
            child_groups_query = text("""
                SELECT g2.id
                FROM res_group g1
                JOIN res_group g2 ON g2.parent = g1.id
                JOIN "res_user-res_group" ugr ON ugr."group" = g1.id
                WHERE ugr."user" = :user_id
            """)
            child_groups = db.execute(child_groups_query, {"user_id": user["id"]}).fetchall()
            child_group_ids = [c[0] for c in child_groups]

            if group_id not in child_group_ids:
                raise HTTPException(status_code=403, detail="Access denied. You can only add users to your child groups.")

            groups_to_check = child_group_ids

        # Step 4: Add users to the group(s)
        for user_id in data.user_ids:
            for group_to_check in groups_to_check:
                # Check if the user is already in the group
                check_query = text("""
                    SELECT 1 FROM "res_user-res_group"
                    WHERE "user" = :user AND "group" = :group
                """)
                existing = db.execute(check_query, {"user": user_id, "group": group_to_check}).fetchone()

                # If user is not in the group, add them
                if not existing:
                    db.execute(text("""
                        INSERT INTO "res_user-res_group" ("user", "group", create_date, create_uid)
                        VALUES (:user, :group, :create_date, :uid)
                    """), {
                        "user": user_id,
                        "group": group_to_check,
                        "create_date": now,
                        "uid": user["id"]
                    })
                else:
                    # Optionally log that user is already in the group
                    print(f"User {user_id} is already in group {group_to_check}.")

        db.commit()  # Commit all changes at once after all insertions.
        return {"success": True, "message": "Users added to group successfully"}

    except Exception as e:
        db.rollback()  # Rollback if any exception occurs
        raise HTTPException(status_code=500, detail=f"Error adding users to group: {str(e)}")

# add groups to user
class AddGroupsToUserRequest(BaseModel):
    group_ids: list[int]
    
@router.post("/users/{user_id}/add-groups")
async def add_groups_to_user(
    user_id: int,
    data: AddGroupsToUserRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    try:
        now = datetime.now()

        # Step 1: Check if user is part of 'Administration'
        is_admin_query = text("""
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name LIKE '%Administration%' AND ugr."user" = :user_id
            LIMIT 1
        """)
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()

        if not is_admin:
            raise HTTPException(status_code=403, detail="Access denied. Not part of Administration group.")

        # Step 2: Check if user is Direct Administration
        is_direct_admin_query = text("""
            SELECT 1
            FROM "res_user-res_group"
            WHERE "user" = :user_id
            AND "group" = (SELECT id FROM res_group WHERE name = 'Administration' LIMIT 1)
            LIMIT 1
        """)
        is_direct_admin = db.execute(is_direct_admin_query, {"user_id": user["id"]}).first()

        # Step 3: Normal Admin (Can add to child groups) or Direct Admin (Can add to any group)
        if is_direct_admin:
            # ✅ Direct Admin can add to any group
            groups_to_add = data.group_ids
        else:
            # ✅ Normal Admin can only add to child groups
            # Fetch child groups of the admin user
            child_groups_query = text("""
                SELECT g2.id
                FROM res_group g1
                JOIN res_group g2 ON g2.parent = g1.id
                JOIN "res_user-res_group" ugr ON ugr."group" = g1.id
                WHERE ugr."user" = :user_id
            """)
            child_groups = db.execute(child_groups_query, {"user_id": user["id"]}).fetchall()
            child_group_ids = [c[0] for c in child_groups]

            # Filter the group ids to only those that are child groups of the admin user
            groups_to_add = [group_id for group_id in data.group_ids if group_id in child_group_ids]

            if not groups_to_add:
                raise HTTPException(status_code=403, detail="Access denied. You can only add users to your child groups.")

        # Step 4: Add groups to the user
        for group_id in groups_to_add:
            # Check if the user is already in the group
            check_query = text("""
                SELECT 1 FROM "res_user-res_group"
                WHERE "user" = :user AND "group" = :group
            """)
            existing = db.execute(check_query, {"user": user_id, "group": group_id}).fetchone()

            # If the user is not in the group, insert the new relationship
            if not existing:
                db.execute(text("""
                    INSERT INTO "res_user-res_group" ("user", "group", create_date, create_uid)
                    VALUES (:user, :group, :create_date, :uid)
                """), {
                    "user": user_id,
                    "group": group_id,
                    "create_date": now,
                    "uid": user["id"]
                })
            else:
                # Optionally, log or handle when the user is already in the group
                print(f"User {user_id} is already in group {group_id}")

        db.commit()  # Commit changes after all insertions
        return {"success": True, "message": "Groups added to user successfully"}

    except Exception as e:
        db.rollback()  # Rollback if any exception occurs
        raise HTTPException(status_code=500, detail=f"Error adding groups to user: {str(e)}")

# get group by user id
@router.get("/users/{user_id}/groups")
async def get_groups_by_user_id(
    user_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Retrieve all groups associated with a user by their user ID,
    but only if the current user is part of the 'Administration' group.
    """
    try:
        # Step 1: Check if the current user is part of the 'Administration' group
        is_admin_query = text("""
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name LIKE '%Administration%' AND ugr."user" = :user_id
            LIMIT 1
        """)
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()
        

        # If the user is not part of the 'Administration' group, deny access
        if not is_admin:
            raise HTTPException(status_code=403, detail="Access denied. Not part of Administration group.")

        # Step 2: Fetch all groups associated with the user
        groups_query = text("""
            SELECT g.id, g.name, g.active, g.create_date, g.parent
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE ugr."user" = :user_id
        """)
        groups_data = db.execute(groups_query, {"user_id": user_id}).fetchall()

        if not groups_data:
            raise HTTPException(status_code=404, detail="No groups found for this user.")

        # Prepare the list of groups
        groups = []
        for group in groups_data:
            groups.append({
                "id": group.id,
                "name": group.name,
                "active": group.active,
                "create_date": str(group.create_date),
                "parent": group.parent
            })

        # Return the list of groups
        return {"success": True, "groups": groups}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving groups: {str(e)}")

# get users by group
@router.get("/groups/{group_id}/users")
async def get_users_by_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Retrieve all users associated with a specific group by group ID,
    but only if the current user is part of the 'Administration' group.
    """
    try:
        # Step 1: Check if the current user is part of the 'Administration' group
        is_admin_query = text("""
            SELECT 1
            FROM res_group g
            JOIN "res_user-res_group" ugr ON ugr."group" = g.id
            WHERE g.name LIKE '%Administration%' AND ugr."user" = :user_id
            LIMIT 1
        """)
        is_admin = db.execute(is_admin_query, {"user_id": user["id"]}).first()

        # If the user is not part of the 'Administration' group, deny access
        if not is_admin:
            raise HTTPException(status_code=403, detail="Access denied. Not part of Administration group.")

        # Step 2: Fetch all users associated with the specified group using the provided query
        users_query = text("""
            SELECT u.id, u.name
            FROM res_user u
            JOIN "res_user-res_group" ugr ON ugr."user" = u.id
            WHERE ugr."group" = :group_id
        """)
        users_data = db.execute(users_query, {"group_id": group_id}).fetchall()

        if not users_data:
            raise HTTPException(status_code=404, detail="No users found for this group.")

        # Prepare the list of users
        users = []
        for user_row in users_data:
            users.append({
                "id": user_row.id,
                "name": user_row.name
            })

        # Return the list of users
        return {"success": True, "users": users}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving users: {str(e)}")

# end

# @router.get("/permissions")
# async def list_permissions():
#     return {"message": "List all permissions"}


# @router.get("/groups/{role_id}/permissions")
# async def get_role_permissions(role_id: int):
#     return {"message": f"List permissions for role {role_id}"}


# @router.post("/groups/{role_id}/permissions")
# async def assign_permissions(role_id: int):
#     return {"message": f"Assign permissions to role {role_id}"}


# @router.put("/users/{user_id}/role")
# async def assign_role_to_user(user_id: int):
#     return {"message": f"Assign role to user {user_id}"}
