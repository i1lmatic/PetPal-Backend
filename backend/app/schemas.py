from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    phone: str


class UserCreate(UserBase):
    password: str


class VetRegisterRequest(UserCreate):
    business_name: str = ""
    business_address: str = ""
    business_phone: str = ""
    business_specialties: str = ""
    business_description: Optional[str] = None
    business_working_hours: Optional[str] = None


class PendingVetOut(BaseModel):
    user_id: int
    email: str
    full_name: str
    phone: str
    business_name: str = ""
    business_address: str = ""
    business_phone: str = ""
    business_specialties: str = ""
    business_description: Optional[str] = None
    business_working_hours: Optional[str] = None


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


class VeterinaryBase(BaseModel):
    name: str
    address: str
    phone: str
    specialties: str
    description: Optional[str] = None
    working_hours: Optional[str] = None
    photo_url: Optional[str] = None
    status: Optional[str] = "active"


class VeterinaryCreate(VeterinaryBase):
    pass


class VeterinaryUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    specialties: Optional[str] = None
    description: Optional[str] = None
    working_hours: Optional[str] = None
    photo_url: Optional[str] = None
    status: Optional[str] = None


class VeterinarySearch(BaseModel):
    q: str


class VeterinaryOut(VeterinaryBase):
    id: int
    owner_user_id: int
    owner_name: Optional[str] = None

    class Config:
        from_attributes = True


class PetBase(BaseModel):
    name: str = ""
    species: str = ""
    breed: str = ""
    birth_date: str = ""
    weight: float = 0.0
    photo_url: Optional[str] = None


class PetCreate(PetBase):
    sex: str
    color: str
    size: str
    allergies: Optional[str] = None
    conditions: Optional[str] = None
    microchip: Optional[str] = None

class PetUpdate(BaseModel):
    name: Optional[str] = None
    species: Optional[str] = None
    breed: Optional[str] = None
    birth_date: Optional[str] = None
    weight: Optional[float] = None
    photo_url: Optional[str] = None
    sex: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    allergies: Optional[str] = None
    conditions: Optional[str] = None
    microchip: Optional[str] = None
    status: Optional[str] = None

class PetOut(PetBase):
    id: int
    owner_id: int
    sex: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    allergies: Optional[str] = None
    conditions: Optional[str] = None
    microchip: Optional[str] = None
    status: Optional[str] = "active"

    class Config:
        from_attributes = True


class PetWithOwner(PetBase):
    id: int
    owner_id: int
    owner_name: Optional[str] = None
    sex: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    allergies: Optional[str] = None
    conditions: Optional[str] = None
    microchip: Optional[str] = None
    status: Optional[str] = "active"

    class Config:
        from_attributes = True

class AppointmentBase(BaseModel):
    pet_id: int
    vet_id: int
    date_time: datetime
    reason: str
    notes: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentOut(AppointmentBase):
    id: int
    owner_id: int
    status: str
    owner_name: Optional[str] = None
    pet_name: Optional[str] = None
    has_record: bool = False
    vet_id: Optional[int] = None
    notes: Optional[str] = None

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
    appointment_id: Optional[int] = None
    vet_id: Optional[int] = None

class VetMedicalRecordCreate(BaseModel):
    appointment_id: int
    diagnosis: str
    treatment: str
    notes: str

class MedicalRecordOut(MedicalRecordBase):
    id: int
    date: datetime
    appointment_id: Optional[int] = None
    vet_id: Optional[int] = None

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    total_users: int = 0
    total_pets: int = 0
    total_appointments: int = 0
    appointments_today: int = 0
    pending_appointments: int = 0
    pending_users: int = 0
    total_vets_active: int = 0
    confirmed_appointments: int = 0
    completed_appointments: int = 0
    cancelled_appointments: int = 0