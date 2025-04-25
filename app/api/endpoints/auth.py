from jose import jwt, JWTError
import datetime
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from ..models.base import get_db
from ..models.base import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
TOKEN_BLACKLIST = set()

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

def create_jwt_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_jwt_token(token: str):
    if token in TOKEN_BLACKLIST:
        raise HTTPException(status_code=401, detail="Token is blacklisted")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """ User login and JWT token generation """

    login_field = form_data.username  # OAuth2 form expects `username`

    user_query = text("SELECT id, name, login, password_hash, otp_verified FROM res_user WHERE login = :login")
    user = db.execute(user_query, {"login": login_field}).fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    ###############################################################
    if user.otp_verified != "true":
        return {"user": "Registration is not Completed"}
    
    ##############################################################

    if not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")

    # Get party ID from user
    internal_user = user.id

    # Debugging
    print(f"🔹 Internal User (res_user.id): {internal_user}")

    # Fetch party information for role determination
    party_query = text("SELECT is_healthprof, is_patient FROM party_party WHERE internal_user = :internal_user")
    party_info = db.execute(party_query, {"internal_user": internal_user}).fetchone()

    if not party_info:
        raise HTTPException(status_code=401, detail="Party information not found")

    is_healthprof, is_patient = party_info

    role = "unknown"

    # Check if the user is a health professional (doctor)
    if is_healthprof:
        role = "doctor"
    elif is_patient:
        role = "patient"

    user_data = {
        "id": user.id,
        "name": user.name,
        "login": user.login,
        "role": role
    }

    token = create_jwt_token(user_data)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_data
    }



@router.get("/me")
def get_current_user(token: str = Depends(oauth2_scheme)):
    user_data = decode_jwt_token(token)
    return {"user": user_data}



@router.post("/logout")
def logout(token: str = Depends(oauth2_scheme)):
    TOKEN_BLACKLIST.add(token)
    return {"message": "Successfully logged out"}
