from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import time
import logging
from app.api.config import settings
from app.api.endpoints import (
    patient_booked_slot_by_date12, patient_search_doctor_list_by_department12, users, appointments, auth, available_slots_telem_phy,
    patient_appointment_cancel_request, patient_appointment_reschedule_request,
    booking_available_appointment_slots, all_specialty_show, doctor_checkavailable_slot_date, otp_verify,
    prescriptions,
    patient_booked_slot_by_date as patient_booked_slots
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="GNU Health Middleware API for managing healthcare appointments and user data",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted Host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # In production, replace with actual allowed hosts
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"Request: {request.method} {request.url} - Processed in {process_time:.4f} seconds")
    return response

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred"}
    )

# Include routers
app.include_router(users.router, prefix=settings.API_V1_STR, tags=["Users"])
app.include_router(appointments.router, prefix=settings.API_V1_STR, tags=["Appointments"])
app.include_router(available_slots_telem_phy.router, prefix=settings.API_V1_STR, tags=["Appointment Slots"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(patient_booked_slots.router, prefix="/api", tags=["patient_booked_slots"])
app.include_router(patient_booked_slot_by_date12.router, prefix=settings.API_V1_STR, tags=["Patient Appointments"])
app.include_router(doctor_checkavailable_slot_date.router, prefix=settings.API_V1_STR, tags=["Doctor Appointments"])
app.include_router(patient_appointment_cancel_request.router, prefix=settings.API_V1_STR, tags=["Appointment Management"])
app.include_router(patient_appointment_reschedule_request.router, prefix=settings.API_V1_STR, tags=["Appointment Management"])
app.include_router(booking_available_appointment_slots.router, prefix=settings.API_V1_STR, tags=["Appointment Booking"])
app.include_router(patient_search_doctor_list_by_department12.router, prefix=settings.API_V1_STR, tags=["Doctor Search"])
app.include_router(all_specialty_show.router, prefix=settings.API_V1_STR, tags=["Specialty Information"])
app.include_router(all_specialty_show.public_router, prefix="/public", tags=["Public API"])
app.include_router(prescriptions.router, prefix="/api", tags=["prescriptions"])
app.include_router(otp_verify.router, prefix="/api", tags=["users"])

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
