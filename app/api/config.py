from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # Database settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    # JWT settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    
    # Email settings
    EMAIL_SENDER: str = os.getenv("EMAIL_SENDER", "")
    EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")
    
    # API settings
    API_V1_STR: str = "/api"
    PROJECT_NAME: str = "GNU Health Middleware API"
    
    # CORS settings
    BACKEND_CORS_ORIGINS: list = ["*"]
    
    # Security settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    PASSWORD_HASH_ALGORITHM: str = "bcrypt"
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # Added Keys
    BREVO_API_KEY: str = os.getenv("BREVO_API_KEY", "")
    USER_ID_PASSWORD: str = os.getenv("USER_ID_PASSWORD", "")
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()

# Validate required settings
if not settings.DATABASE_URL:
    raise ValueError("DATABASE_URL must be set in environment variables")
if not settings.JWT_SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY must be set in environment variables")
# Temporarily commented out to allow server startup without email credentials
# if not settings.EMAIL_SENDER or not settings.EMAIL_PASSWORD:
#     raise ValueError("Email credentials must be set in environment variables") 