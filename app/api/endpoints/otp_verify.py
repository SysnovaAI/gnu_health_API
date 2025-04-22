import datetime
import os
from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from fastapi.responses import JSONResponse
from ..models.base import get_db
from datetime import timedelta
from .appointments import get_current_user 
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64
from dotenv import load_dotenv
load_dotenv()

router = APIRouter()
OTP_VALIDATION_TIME = 5  # Minutes

class OPTCODE(BaseModel):
    otp: int


# Create a 256-bit AES key from a password using SHA-256
def get_aes_key_from_password(password: str) -> bytes:
    return hashlib.sha256(password.encode()).digest()

# Decrypt the Base64-safe encrypted string back to integer
def decrypt_int(encrypted_value: str, password: str) -> int:
    # Add padding back to Base64 string if needed
    padded_value = encrypted_value + '=' * (-len(encrypted_value) % 4)
    raw = base64.urlsafe_b64decode(padded_value)  # Decode Base64
    
    key = get_aes_key_from_password(password)
    iv = raw[:16]  # Extract IV
    encrypted_data = raw[16:]  # Extract ciphertext
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = unpad(cipher.decrypt(encrypted_data), AES.block_size)
    
    return int(decrypted.decode())

# @router.post("/verify-otp")
@router.post("/verify-otp/{user_id}")
def otp_verifications(otp: OPTCODE, user_id: str = Path(...), db: Session = Depends(get_db)):#, user: dict = Depends(get_current_user)):
    otp = otp.otp
    print(user_id)
    user_id = decrypt_int(user_id, os.getenv("USER_ID_PASSWORD"))
    # Get current server time in Asia/Dhaka timezone
    server_time_stmt = text("SELECT NOW() AT TIME ZONE 'Asia/Dhaka';")
    current_time = db.execute(server_time_stmt).fetchone()[0]
    print(current_time)

    # Fetch OTP info from the database
    otp_info_stmt = text("""
        SELECT otp_number, otp_date, otp_verified
        FROM res_user
        WHERE id = :user_id;
    """)
    otp_info = db.execute(otp_info_stmt, {"user_id": user_id}).fetchone()

    if otp_info is None:
        return JSONResponse(
            content={"status": False, "message": "User not found"},
            status_code=404
        )

    otp_number, otp_date, otp_status = otp_info

    # Check if the OTP is within the valid time window
    if (current_time - otp_date) <= timedelta(minutes=OTP_VALIDATION_TIME):
        if otp_number == otp:
            # Update verification status
            otp_update_stmt = text("""
                UPDATE res_user
                SET otp_verified = :otp_status
                WHERE id = :user_id;
            """)
            db.execute(otp_update_stmt, {
                "otp_status": True,
                "user_id": user_id
            })
            db.commit()
            return JSONResponse(content={"status": True, "message": "Verified"}, status_code=200)
        else:
            return JSONResponse(content={"status": False, "message": "Incorrect OTP"}, status_code=200)
    else:
        return JSONResponse(content={"status": False, "message": "OTP Expired"}, status_code=200)


