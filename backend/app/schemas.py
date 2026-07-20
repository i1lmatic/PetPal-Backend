from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    phone: str

class UserCreate(UserBase):
    password: str

class UserUpdateProfile(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None

class UserUpdateStatus(BaseModel):
    status: str

class UserOut(UserBase):
    id: int
    role: str
    status: str

    class Config:
        from_attributes = True

class UserDetail(BaseModel):
    id: int
    email: str
    full_name: str
    phone: str
    role: str
    status: str
    pets: List["PetOut"] = []

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class PetBase(BaseModel):
    name: str
    species: str
    breed: str
    birth_date: str
    weight: float
    photo_url: Optional[str] = None

class PetCreate(PetBase):
    pass

class PetOut(PetBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True

class PetWithOwner(PetBase):
    id: int
    owner_id: int
    owner_name: Optional[str] = None

    class Config:
        from_attributes = True

class AppointmentBase(BaseModel):
    pet_id: int
    date_time: datetime
    reason: str

class AppointmentCreate(AppointmentBase):
    pass

class AppointmentOut(AppointmentBase):
    id: int
    owner_id: int
    status: str
    owner_name: Optional[str] = None
    pet_name: Optional[str] = None

    class Config:
        from_attributes = True

class AppointmentUpdateStatus(BaseModel):
    status: str

class MedicalRecordBase(BaseModel):
    pet_id: int
    diagnosis: str
    treatment: str
    notes: str

class MedicalRecordCreate(MedicalRecordBase):
    pass

class MedicalRecordOut(MedicalRecordBase):
    id: int
    date: datetime

    class Config:
        from_attributes = True

class DashboardStats(BaseModel):
    total_users: int = 0
    total_pets: int = 0
    total_appointments: int = 0
    appointments_today: int = 0
    pending_appointments: int = 0
    pending_users: int = 0
