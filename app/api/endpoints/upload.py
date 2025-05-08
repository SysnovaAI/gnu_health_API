from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from ..models.base import get_db
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from datetime import datetime
from uuid import uuid4
import os

router = APIRouter()

# Upload image and get path
@router.post("/api/upload")
def upload_image(
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not image.filename:
        raise HTTPException(status_code=400, detail="No image file provided")

    upload_dir = "base_url/blog_image"
    os.makedirs(upload_dir, exist_ok=True)

    filename = image.filename
    file_path = os.path.join(upload_dir, filename)

    # Generate unique filename if file already exists
    if os.path.exists(file_path):
        filename = f"{uuid4().hex}_{filename}"
        file_path = os.path.join(upload_dir, filename)

    # Save the file
    with open(file_path, "wb") as f:
        f.write(image.file.read())

    # Return the image information
    return {
        "success": True,
        "message": "Image uploaded successfully",
        "image": {
            "name": filename,
            "path": f"/blog_image/{filename}"
        }
    } 