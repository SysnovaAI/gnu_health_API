from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from ..models.base import get_db, SECRET_KEY
from datetime import datetime
from uuid import uuid4
import os
from fastapi import Form, UploadFile, File
from typing import Optional
import dotenv

dotenv.load_dotenv()

BASE_URL_blog = os.getenv("BASE_URL_blog")

UPLOAD_FOLDER = "blog_image"

router = APIRouter()

ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        user_id = payload.get("id")
        user_name = payload.get("name")
        login = payload.get("login")
        role = payload.get("role")

        if not user_id or not role:
            raise HTTPException(status_code=401, detail="Missing user info in token")

        # Debug log (remove or log securely in production)
        print(f"✅ Decoded Token: ID={user_id}, Name={user_name}, Role={role}")

        return {
            "id": user_id,
            "name": user_name,
            "login": login,
            "role": role
        }

    except JWTError as e:
        print("JWT Decode Error:", str(e))
        raise HTTPException(status_code=401, detail="Invalid token or expired session")

# Fetch all blog posts (public, no auth required)
@router.post("/all_blogs")
def fetch_all_blogs(db: Session = Depends(get_db)):
    try:
        query = text("""
            SELECT b.*, 
                   u.name as author_name, 
                   CASE 
                       WHEN b.image_name IS NOT NULL THEN b.image_name
                       ELSE NULL 
                   END as image_name_only
            FROM blog_post b
            LEFT JOIN res_user u ON b.author_id = u.id
            ORDER BY b.created_at DESC
        """)
        blogs = db.execute(query).fetchall()
        blogs_out = []
        for blog in blogs:
            blog_dict = dict(blog._mapping)
            blog_dict["image_path"] = get_full_image_url(blog_dict.get("image_name_only"))
            # Fetch approved comments for this blog
            comments_query = text("""
                SELECT 
                    c.*, u.name as commenter_name, b.id as blog_id, b.title as blog_title
                FROM blog_comment c
                LEFT JOIN res_user u ON c.commenter_id = u.id
                LEFT JOIN blog_post b ON c.blog_id = b.id
                WHERE c.blog_id = :blog_id 
                AND c.status = 'approved'
                ORDER BY c.created_at ASC
            """)
            comments = db.execute(comments_query, {"blog_id": blog_dict["id"]}).fetchall()
            blog_dict["comments"] = [dict(comment._mapping) for comment in comments]
            blogs_out.append(blog_dict)
        return {"blogs": blogs_out}
    except Exception as e:
        print(f"Error fetching blogs: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch blogs")


# Create a new blog post
@router.post("/blogs")
def create_blog(
    title: str = Form(...),
    content: str = Form(...),
    meta_title: str = Form(""),
    meta_description: str = Form(""),
    meta_keywords: str = Form(""),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    image_name = None
    image_path = None

    if image and image.filename:
        upload_dir = "blog_image"
        os.makedirs(upload_dir, exist_ok=True)

        filename = image.filename
        file_path = os.path.join(upload_dir, filename)

        if os.path.exists(file_path):
            filename = f"{uuid4().hex}_{filename}"
            file_path = os.path.join(upload_dir, filename)

        with open(file_path, "wb") as f:
            f.write(image.file.read())

        image_name = filename
        image_path = f"/blog_image/{filename}"

    # Insert blog post with default status = "pending"
    query = text("""
        INSERT INTO blog_post 
        (title, content, image_name, meta_title, meta_description, meta_keywords, author_id, status)
        VALUES (:title, :content, :image_name, :meta_title, :meta_description, :meta_keywords, :author_id, :status)
        RETURNING id
    """)
    result = db.execute(query, {
        "title": title,
        "content": content,
        "image_name": image_name,
        "meta_title": meta_title,
        "meta_description": meta_description,
        "meta_keywords": meta_keywords,
        "author_id": current_user["id"],
        "status": "pending"
    })
    db.commit()
    
    blog_id = result.scalar()

    return {
        "success": True,
        "message": "Blog created successfully",
        "blog_id": blog_id,
        "image": {
            "name": image_name,
            "path": image_path
        } if image_name else None
    }


# Helper to get full image URL
def get_full_image_url(image_name: Optional[str]) -> Optional[str]:
    if image_name:
        return f"{BASE_URL_blog}/blog_image/{image_name}"
    return None


# Fetch single blog post by ID (public, no auth required)
@router.post("/blogs/{id}")
def fetch_blog(id: int, db: Session = Depends(get_db)):
    blog_query = text("""
        SELECT 
            b.*, u.name as author_name,
            CASE WHEN b.image_name IS NOT NULL THEN b.image_name ELSE NULL END as image_name_only
        FROM blog_post b
        LEFT JOIN res_user u ON b.author_id = u.id
        WHERE b.id = :id
    """)
    blog = db.execute(blog_query, {"id": id}).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    blog_dict = dict(blog._mapping)
    blog_dict["image_path"] = get_full_image_url(blog_dict.get("image_name_only"))

    # Fetch approved comments with commenter details and blog info
    comments_query = text("""
        SELECT 
            c.*, u.name as commenter_name, b.id as blog_id, b.title as blog_title
        FROM blog_comment c
        LEFT JOIN res_user u ON c.commenter_id = u.id
        LEFT JOIN blog_post b ON c.blog_id = b.id
        WHERE c.blog_id = :blog_id 
        AND c.status = 'approved'
        ORDER BY c.created_at ASC
    """)
    comments = db.execute(comments_query, {"blog_id": id}).fetchall()
    comments_list = [dict(comment._mapping) for comment in comments]

    return {
        "blog": blog_dict,
        "comments": comments_list
    }

# Update a blog post
@router.put("/api/blogs/{id}")
def update_blog(
    id: int,
    title: str = None,
    content: str = None,
    meta_title: str = None,
    meta_description: str = None,
    meta_keywords: str = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    blog_query = text("SELECT author_id FROM blog_post WHERE id = :id")
    blog = db.execute(blog_query, {"id": id}).first()

    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    if blog.author_id != current_user["id"]:
        print(blog.author_id,current_user["id"])
        raise HTTPException(status_code=403, detail="Not authorized to update this blog")

    update_query = text("""
        UPDATE blog_post SET
            title = COALESCE(:title, title),
            content = COALESCE(:content, content),
            meta_title = COALESCE(:meta_title, meta_title),
            meta_description = COALESCE(:meta_description, meta_description),
            meta_keywords = COALESCE(:meta_keywords, meta_keywords),
            updated_at = NOW()
        WHERE id = :id
    """)
    db.execute(update_query, {
        "id": id,
        "title": title,
        "content": content,
        "meta_title": meta_title,
        "meta_description": meta_description,
        "meta_keywords": meta_keywords
    })
    db.commit()
    return {"success": True, "message": "Blog updated successfully"}

# Delete a blog post
@router.delete("/api/blogs/{id}")
def delete_blog(id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    blog_query = text("SELECT author_id FROM blog_post WHERE id = :id")
    blog = db.execute(blog_query, {"id": id}).first()

    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")

    # Access using blog._mapping["author_id"]
    if blog._mapping["author_id"] != current_user["id"] and not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to delete this blog")

    delete_query = text("DELETE FROM blog_post WHERE id = :id")
    db.execute(delete_query, {"id": id})
    db.commit()

    return {"success": True, "message": "Blog deleted successfully"}


# Add comment to a blog - Anyone can comment
@router.post("/api/blogs/{blog_id}/comments/")
def add_comment(
    blog_id: int, 
    comment: str = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Check if blog exists
    blog_query = text("SELECT id FROM blog_post WHERE id = :blog_id")
    blog = db.execute(blog_query, {"blog_id": blog_id}).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")

    insert_query = text("""
        INSERT INTO blog_comment 
        (blog_id, commenter_id, comment, status, approved_by, created_at)
        VALUES (:blog_id, :commenter_id, :comment, 'pending', 0, NOW())
    """)
    db.execute(insert_query, {
        "blog_id": blog_id,
        "commenter_id": current_user["id"],
        "comment": comment
    })
    db.commit()
    return {"success": True, "message": "Comment added, awaiting approval"}

# Approve a comment - Only blog author can approve
@router.put("/api/comments/{comment_id}/approve")
def approve_comment(
    comment_id: int, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Get the comment and its associated blog
    comment_query = text("""
        SELECT c.id, c.blog_id, b.author_id 
        FROM blog_comment c
        JOIN blog_post b ON c.blog_id = b.id
        WHERE c.id = :comment_id
    """)
    result = db.execute(comment_query, {"comment_id": comment_id}).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # Check if current user is the blog author
    if result.author_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only the blog author can approve comments")

    update_query = text("""
        UPDATE blog_comment 
        SET status = 'approved', 
            approved_by = :author_id 
        WHERE id = :comment_id
    """)
    db.execute(update_query, {
        "comment_id": comment_id,
        "author_id": current_user["id"]
    })
    db.commit()
    return {"success": True, "message": "Comment approved"}

# Reject a comment - Only blog author can reject
@router.put("/api/comments/{comment_id}/reject")
def reject_comment(
    comment_id: int, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Get the comment and its associated blog
    comment_query = text("""
        SELECT c.id, c.blog_id, b.author_id 
        FROM blog_comment c
        JOIN blog_post b ON c.blog_id = b.id
        WHERE c.id = :comment_id
    """)
    result = db.execute(comment_query, {"comment_id": comment_id}).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # Check if current user is the blog author
    if result.author_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only the blog author can reject comments")

    update_query = text("""
        UPDATE blog_comment 
        SET status = 'rejected', 
            approved_by = :author_id 
        WHERE id = :comment_id
    """)
    db.execute(update_query, {
        "comment_id": comment_id,
        "author_id": current_user["id"]
    })
    db.commit()
    return {"success": True, "message": "Comment rejected"}

# Fetch all approved comments for a blog - Anyone can view
@router.get("/api/blogs/{blog_id}/comments/")
def fetch_approved_comments(blog_id: int, db: Session = Depends(get_db)):
    # Check if blog exists
    blog_query = text("SELECT id FROM blog_post WHERE id = :blog_id")
    blog = db.execute(blog_query, {"blog_id": blog_id}).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")

    query = text("""
        SELECT id, blog_id, commenter_id, comment, status, approved_by, created_at
        FROM blog_comment
        WHERE blog_id = :blog_id
        ORDER BY created_at ASC
    """)
    comments = db.execute(query, {"blog_id": blog_id}).fetchall()
    return {"comments": [dict(comment._mapping) for comment in comments]}

# Approve a blog post - Only administrators can approve
@router.put("/api/{blog_id}/approve")
def approve_blog(
    blog_id: int, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != "Administration":
        raise HTTPException(status_code=403, detail="Only administrators can approve blogs")

    # Check if blog exists
    blog_query = text("SELECT id FROM blog_post WHERE id = :blog_id")
    blog = db.execute(blog_query, {"blog_id": blog_id}).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")

    update_query = text("""
        UPDATE blog_post 
        SET status = 'approved',
            updated_at = NOW()
        WHERE id = :blog_id
    """)
    db.execute(update_query, {"blog_id": blog_id})
    db.commit()
    return {"success": True, "message": "Blog approved successfully"}

# Reject a blog post - Only administrators can reject
@router.put("/api/{blog_id}/reject")
def reject_blog(
    blog_id: int, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != "Administration":
        raise HTTPException(status_code=403, detail="Only administrators can reject blogs")

    # Check if blog exists
    blog_query = text("SELECT id FROM blog_post WHERE id = :blog_id")
    blog = db.execute(blog_query, {"blog_id": blog_id}).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")

    update_query = text("""
        UPDATE blog_post 
        SET status = 'rejected',
            updated_at = NOW()
        WHERE id = :blog_id
    """)
    db.execute(update_query, {"blog_id": blog_id})
    db.commit()
    return {"success": True, "message": "Blog rejected successfully"}

# Author-only: fetch all comments for a blog (any status)
@router.get("/api/blogs/{blog_id}/all_comments")
def fetch_all_comments_for_blog(blog_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Check if current user is the author
    blog_query = text("SELECT author_id FROM blog_post WHERE id = :blog_id")
    blog = db.execute(blog_query, {"blog_id": blog_id}).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    if blog.author_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only the blog author can view all comments")

    comments_query = text("""
        SELECT 
            c.*, u.name as commenter_name, b.id as blog_id, b.title as blog_title
        FROM blog_comment c
        LEFT JOIN res_user u ON c.commenter_id = u.id
        LEFT JOIN blog_post b ON c.blog_id = b.id
        WHERE c.blog_id = :blog_id
        ORDER BY c.created_at ASC
    """)
    comments = db.execute(comments_query, {"blog_id": blog_id}).fetchall()
    comments_list = [dict(comment._mapping) for comment in comments]
    return {"comments": comments_list}
