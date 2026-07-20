from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, Enum
from sqlalchemy.orm import relationship
from .database import Base
import enum

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CLIENT = "client"

class UserStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    REJECTED = "rejected"

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
    role = Column(String, default=UserRole.CLIENT)
    status = Column(String, default=UserStatus.PENDING)

    pets = relationship("Pet", back_populates="owner")
    appointments = relationship("Appointment", back_populates="owner")

class Pet(Base):
    __tablename__ = "pets"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    species = Column(String)
    breed = Column(String)
    birth_date = Column(String)  # For simplicity, using string for now
    weight = Column(Float)
    photo_url = Column(String, nullable=True)

    owner = relationship("User", back_populates="pets")
    medical_records = relationship("MedicalRecord", back_populates="pet")
    appointments = relationship("Appointment", back_populates="pet")

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer, ForeignKey("pets.id"))
    owner_id = Column(Integer, ForeignKey("users.id"))
    date_time = Column(DateTime)
    reason = Column(String)
    status = Column(String, default=AppointmentStatus.PENDING)

    pet = relationship("Pet", back_populates="appointments")
    owner = relationship("User", back_populates="appointments")

class MedicalRecord(Base):
    __tablename__ = "medical_records"

    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer, ForeignKey("pets.id"))
    date = Column(DateTime)
    diagnosis = Column(String)
    treatment = Column(String)
    notes = Column(String)

    pet = relationship("Pet", back_populates="medical_records")
