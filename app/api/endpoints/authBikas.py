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
############################################
    if user.otp_verified != "true":
        return {"user": "Registration is not Completed"}
#######################################
    if not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")

    # Get party ID from user
    internal_user = user.id

    # Debugging
    print(f"🔹 Internal User (res_user.id): {internal_user}")


    group = text("""select ru.id, rurg.group, rg.name
                    from res_user ru
                    join "res_user-res_group" rurg on ru.id = rurg.user
                    join res_group rg on rurg.group = rg.id
                    where ru.id = :user_id""")
    
    group_result = db.execute(group, {"user_id": user.id}).fetchall()
    
    group_list = [{"id": row.id, "group_id": row.group, "group_name": row.name} for row in group_result]

    group_role = group_result[0].name if group_result else None

    role = "unknown"

    if group_role is not None:
        group_role = group_role.split(" ")

        if len(group_role)>=1:
            role = group_role[-1]
        else:
            role = group_role

    user_data = {
        "id": user.id,
        "name": user.name,
        "login": user.login,
        "role": role
    }


    token = create_jwt_token(user_data)

    return {
        "status": "Congratulation Login Successfully !!!",
        "access_token": token,
        "token_type": "bearer",
        "user": user_data,
        "group": group_list
    }



@router.get("/me")
def get_current_user(token: str = Depends(oauth2_scheme)):
    user_data = decode_jwt_token(token)
    return {"user": user_data}



@router.post("/logout")
def logout(token: str = Depends(oauth2_scheme)):
    TOKEN_BLACKLIST.add(token)
    return {"message": "Successfully logged out"}
