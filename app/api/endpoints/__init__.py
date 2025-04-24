from fastapi import APIRouter
from .appointments import router as appointments_router
from .prescriptions import router as prescriptions_router
from .prescription_save import router as prescription_save_router

router = APIRouter()

router.include_router(appointments_router, prefix="/api", tags=["appointments"])
router.include_router(prescriptions_router, prefix="/api", tags=["prescriptions"])
router.include_router(prescription_save_router, prefix="/api", tags=["prescription_save"])
