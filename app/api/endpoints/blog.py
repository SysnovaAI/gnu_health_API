from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from ..models.base import get_db, SECRET_KEY
from datetime import datetime

router = APIRouter()

ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found in token")
        return {"id": user_id}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token or expired session")


# Create a new blog post
@router.post("/api/blogs/")
def create_blog(title: str, content: str, meta_title: str = '', meta_description: str = '', meta_keywords: str = '', db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
	query = text("""
    	INSERT INTO blog_post (title, content, meta_title, meta_description, meta_keywords, author_id)
    	VALUES (:title, :content, :meta_title, :meta_description, :meta_keywords, :author_id)
	""")
	db.execute(query, {
    	"title": title,
    	"content": content,
    	"meta_title": meta_title,
    	"meta_description": meta_description,
    	"meta_keywords": meta_keywords,
    	"author_id": current_user["id"]
	})
	db.commit()
	return {"success": True, "message": "Blog created successfully"}

# Fetch all blog posts
@router.get("/api/blogs/")
def fetch_all_blogs(db: Session = Depends(get_db)):
	query = text("SELECT id, title, meta_title, created_at FROM blog_post ORDER BY created_at DESC")
	blogs = db.execute(query).fetchall()
	return {"blogs": [dict(blog._mapping) for blog in blogs]}

# Fetch single blog post by ID
@router.get("/api/blogs/{id}")
def fetch_blog(id: int, db: Session = Depends(get_db)):
    query = text("SELECT * FROM blog_post WHERE id = :id")
    blog = db.execute(query, {"id": id}).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    return {"blog": dict(blog._mapping)}

# Update a blog post
@router.put("/api/blogs/{id}")
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
def delete_blog(
    id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    blog_query = text("SELECT author_id FROM blog_post WHERE id = :id")
    blog = db.execute(blog_query, {"id": id}).first()

    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    if blog.author_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete this blog")

    delete_query = text("DELETE FROM blog_post WHERE id = :id")
    db.execute(delete_query, {"id": id})
    db.commit()

    return {"success": True, "message": "Blog deleted successfully"}

# Add comment to a blog
@router.post("/api/blogs/{blog_id}/comments/")
def add_comment(blog_id: int, comment: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
	insert_query = text("""
    	INSERT INTO blog_comment (blog_id, commenter_id, comment)
    	VALUES (:blog_id, :commenter_id, :comment)
	""")
	db.execute(insert_query, {
    	"blog_id": blog_id,
    	"commenter_id": current_user["id"],
    	"comment": comment
	})
	db.commit()
	return {"success": True, "message": "Comment added, awaiting approval"}

# Approve a comment
@router.put("/api/comments/{comment_id}/approve")
def approve_comment(comment_id: int, db: Session = Depends(get_db)):
	update_query = text("UPDATE blog_comment SET status = 'approved' WHERE id = :comment_id")
	db.execute(update_query, {"comment_id": comment_id})
	db.commit()
	return {"success": True, "message": "Comment approved"}

# Reject a comment
@router.put("/api/comments/{comment_id}/reject")
def reject_comment(comment_id: int, db: Session = Depends(get_db)):
	update_query = text("UPDATE blog_comment SET status = 'rejected' WHERE id = :comment_id")
	db.execute(update_query, {"comment_id": comment_id})
	db.commit()
	return {"success": True, "message": "Comment rejected"}

# Fetch all approved comments for a blog
@router.get("/api/blogs/{blog_id}/comments/")
def fetch_approved_comments(blog_id: int, db: Session = Depends(get_db)):
	query = text("""
    	SELECT id, commenter_id, comment, created_at
    	FROM blog_comment
    	WHERE blog_id = :blog_id AND status = 'approved'
    	ORDER BY created_at ASC
	""")
	comments = db.execute(query, {"blog_id": blog_id}).fetchall()
	return {"comments": [dict(comment._mapping) for comment in comments]}
