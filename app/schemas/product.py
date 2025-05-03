from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ProductBase(BaseModel):
    name: str
    product_type: str
    quantity: float
    rate: float
    product_supplier: int

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    product_type: Optional[str] = None
    quantity: Optional[float] = None
    rate: Optional[float] = None
    product_supplier: Optional[int] = None

class Product(ProductBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True 