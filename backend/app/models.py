from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from .database import Base
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    SUPERUSER = "superuser"
    VET = "vet"
    CLIENT = "client"


class UserStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    REJECTED = "rejected"


class VeterinaryStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"

class PetStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class AppointmentStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    phone = Column(String)
    role = Column(String, default=UserRole.CLIENT.value)
    status = Column(String, default=UserStatus.PENDING.value)
    accepted_terms = Column(Integer, default=0)

    pets = relationship("Pet", back_populates="owner")
    appointments = relationship("Appointment", back_populates="owner")
    veterinary_business = relationship("Veterinary", back_populates="owner", uselist=False)


class Veterinary(Base):
    __tablename__ = "veterinary"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    specialties = Column(String, nullable=False)
    description = Column(String, nullable=True)
    working_hours = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    status = Column(String, default=VeterinaryStatus.ACTIVE.value)

    owner = relationship("User", back_populates="veterinary_business")
    appointments = relationship("Appointment", back_populates="vet")
    medical_records = relationship("MedicalRecord", back_populates="vet")


class Pet(Base):
    __tablename__ = "pets"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    species = Column(String)
    breed = Column(String)
    birth_date = Column(String)
    weight = Column(Float)
    photo_url = Column(String, nullable=True)

    sex = Column(String, nullable=True)
    color = Column(String, nullable=True)
    size = Column(String, nullable=True)
    allergies = Column(String, nullable=True)
    conditions = Column(String, nullable=True)
    microchip = Column(String, nullable=True)
    status = Column(String, default=PetStatus.ACTIVE.value)

    owner = relationship("User", back_populates="pets")
    medical_records = relationship("MedicalRecord", back_populates="pet")
    appointments = relationship("Appointment", back_populates="pet")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer, ForeignKey("pets.id"))
    owner_id = Column(Integer, ForeignKey("users.id"))
    vet_id = Column(Integer, ForeignKey("veterinary.id"), nullable=True)
    date_time = Column(DateTime)
    reason = Column(String)
    notes = Column(String, nullable=True)
    status = Column(String, default=AppointmentStatus.PENDING.value)

    pet = relationship("Pet", back_populates="appointments")
    owner = relationship("User", back_populates="appointments")
    vet = relationship("Veterinary", back_populates="appointments")


class MedicalRecord(Base):
    __tablename__ = "medical_records"

    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer, ForeignKey("pets.id"))
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    vet_id = Column(Integer, ForeignKey("veterinary.id"), nullable=True)
    date = Column(DateTime)
    diagnosis = Column(String)
    treatment = Column(String)
    notes = Column(String)

    pet = relationship("Pet", back_populates="medical_records")
    appointment = relationship("Appointment", backref="medical_record")
    vet = relationship("Veterinary", back_populates="medical_records")