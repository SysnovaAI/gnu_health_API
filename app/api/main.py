from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import time
import logging
from app.api.config import settings
from app.api.endpoints import (
     appointments, available_slots_telem_phy, blog,users,auth, book_appointment_slot_confirmed,diagnosis_req_lab_test_orders,
    patient_appointment_cancel_request, patient_appointment_reschedule_request,
    booking_available_appointment_slots, all_specialty_show, doctor_checkavailable_slot_date, otp_verify,
    prescriptions, health, generate_slot,
    patient_search_doctor_list_by_department, patient_booked_slot_by_date,
    prescription_save, medicine_list, prescription_test_catagory, patient_prescription,
    product, cart, cart_direct, cart_simple,
    orders, order_details, order_test, ordered_lab_test_view,admin_access_models, admin_groups, admin_orders, profile_update
)
from fastapi.staticfiles import StaticFiles
import os

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
app.include_router(product.router, prefix="/api")
app.include_router(users.router, prefix="/api", tags=["Users"])
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
app.include_router(book_appointment_slot_confirmed.router, prefix=settings.API_V1_STR, tags=["Appointment Booking"])
app.include_router(health.router, prefix=settings.API_V1_STR, tags=["Health"])
app.include_router(generate_slot.router, prefix=settings.API_V1_STR, tags=["Slot Generation"])
app.include_router(prescription_test_catagory.public_router, prefix="/public", tags=["Test Categories"])
app.include_router(medicine_list.public_router, prefix="/public", tags=["Medicines"])
app.include_router(patient_prescription.router, prefix="/api", tags=["Patient Prescriptions"])
app.include_router(blog.router, prefix="/api")
app.include_router(cart.router, prefix="/api", tags=["Cart"])
app.include_router(cart_direct.router, prefix="/api", tags=["Cart Direct"])
app.include_router(cart_simple.router, prefix="/api", tags=["Cart Simple"])
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
app.include_router(order_details.router, prefix="/api/orders", tags=["Order Details"]) 
app.include_router(diagnosis_req_lab_test_orders.router, prefix="/api", tags=["lab test orders"]) 
app.include_router(order_test.router, prefix="/api", tags=["Lab Test Orders"])
app.include_router(ordered_lab_test_view.router, prefix="/api", tags=["Lab Test Order Views"])
app.include_router(diagnosis_req_lab_test_orders.router, prefix="/api", tags=["Diagnostic Center"])
app.include_router(admin_groups.router)
app.include_router(admin_access_models.router)
app.include_router(admin_orders.router)
app.include_router(profile_update.router, prefix=settings.API_V1_STR, tags=["profile Update"])

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

os.makedirs("blog_image", exist_ok=True)
app.mount("/blog_image", StaticFiles(directory="blog_image"), name="blog_image")
