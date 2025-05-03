from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import time
import logging
from app.api.config import settings
from app.api.endpoints import (
    book_appointment_slot_confirmedOLD, prescription_test_catagoryOLD, users, appointments, auth, available_slots_telem_phy,
    patient_appointment_cancel_request, patient_appointment_reschedule_request,
    booking_available_appointment_slots, all_specialty_show, doctor_checkavailable_slot_date, otp_verify,
    prescriptions, health, generate_slot,
    patient_search_doctor_list_by_department, patient_booked_slot_by_date,
    prescription_save, medicine_list, prescription_test_catagory, patient_prescription,
    product, blog
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
@app.middleware("https")
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
app.include_router(product.router, prefix="/api", tags=["Products"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(appointments.router, prefix=settings.API_V1_STR, tags=["Appointments"])
app.include_router(available_slots_telem_phy.router, prefix=settings.API_V1_STR, tags=["Appointment Slots"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(patient_booked_slot_by_date.router, prefix=settings.API_V1_STR, tags=["Patient Appointments"])
app.include_router(doctor_checkavailable_slot_date.router, prefix=settings.API_V1_STR, tags=["Doctor Appointments"])
app.include_router(patient_appointment_cancel_request.router, prefix=settings.API_V1_STR, tags=["Appointment Management"])
app.include_router(patient_appointment_reschedule_request.router, prefix=settings.API_V1_STR, tags=["Appointment Management"])
app.include_router(booking_available_appointment_slots.router, prefix=settings.API_V1_STR, tags=["Appointment Booking"])
app.include_router(patient_search_doctor_list_by_department.router, prefix=settings.API_V1_STR, tags=["Doctor Search"])
app.include_router(all_specialty_show.router, prefix=settings.API_V1_STR, tags=["Specialty Information"])
app.include_router(all_specialty_show.public_router, prefix="/public", tags=["Public API"])
app.include_router(prescriptions.router, prefix="/api", tags=["prescriptions"])
app.include_router(prescription_save.router, prefix="/api", tags=["prescription_save"])
app.include_router(otp_verify.router, prefix="/api", tags=["users"])
app.include_router(book_appointment_slot_confirmedOLD.router, prefix=settings.API_V1_STR, tags=["Appointment Booking"])
app.include_router(health.router, prefix=settings.API_V1_STR, tags=["Health"])
app.include_router(generate_slot.router, prefix=settings.API_V1_STR, tags=["Slot Generation"])
app.include_router(prescription_test_catagory.public_router, prefix="/public", tags=["Test Categories"])
app.include_router(medicine_list.public_router, prefix="/public", tags=["Medicines"])
app.include_router(patient_prescription.router, prefix="/api", tags=["Patient Prescriptions"])
app.include_router(blog.router, prefix="/api", tags=["Blogs"])

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
