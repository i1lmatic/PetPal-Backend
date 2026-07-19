from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List
from datetime import timedelta

from . import models, schemas, auth, database
from .database import engine, get_db

# Crear tablas en SQLite
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="PetPal API")

# --- AUTH ENDPOINTS ---

@app.post("/auth/register", response_model=schemas.UserOut)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email ya registrado")
    
    hashed_pwd = auth.get_password_hash(user.password)
    # El primer usuario podría ser admin para facilitar las pruebas, 
    # pero por ahora todos son clientes pendientes
    new_user = models.User(
        email=user.email,
        hashed_password=hashed_pwd,
        full_name=user.full_name,
        phone=user.phone,
        role=models.UserRole.CLIENT,
        status=models.UserStatus.PENDING
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/auth/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # IMPORTANTE: Bloquear login si no está activo
    auth.check_active(user)
    
    access_token = auth.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", response_model=schemas.UserOut)
def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

# --- ADMIN ENDPOINTS ---

@app.get("/admin/users/pending", response_model=List[schemas.UserOut])
def get_pending_users(
    db: Session = Depends(get_db), 
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    return db.query(models.User).filter(models.User.status == models.UserStatus.PENDING).all()

@app.patch("/admin/users/{user_id}/approve", response_model=schemas.UserOut)
def approve_user(
    user_id: int, 
    db: Session = Depends(get_db), 
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    user.status = models.UserStatus.ACTIVE
    db.commit()
    db.refresh(user)
    return user

@app.get("/admin/appointments", response_model=List[schemas.AppointmentOut])
def get_all_appointments(
    db: Session = Depends(get_db), 
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    return db.query(models.Appointment).all()

@app.post("/admin/medical-records", response_model=schemas.MedicalRecordOut)
def create_medical_record(
    record: schemas.MedicalRecordCreate, 
    db: Session = Depends(get_db), 
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    db_pet = db.query(models.Pet).filter(models.Pet.id == record.pet_id).first()
    if not db_pet:
        raise HTTPException(status_code=404, detail="Mascota no encontrada")
    
    from datetime import datetime
    new_record = models.MedicalRecord(
        **record.dict(),
        date=datetime.utcnow()
    )
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return new_record

# --- CLIENT ENDPOINTS (Mascotas y Citas) ---

@app.post("/pets/", response_model=schemas.PetOut)
def create_pet(
    pet: schemas.PetCreate, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    new_pet = models.Pet(**pet.dict(), owner_id=current_user.id)
    db.add(new_pet)
    db.commit()
    db.refresh(new_pet)
    return new_pet

@app.get("/pets/", response_model=List[schemas.PetOut])
def list_my_pets(
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    return db.query(models.Pet).filter(models.Pet.owner_id == current_user.id).all()

@app.get("/pets/{pet_id}/history", response_model=List[schemas.MedicalRecordOut])
def get_pet_history(
    pet_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    # Verificar que la mascota le pertenezca o sea admin
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Mascota no encontrada")
    
    if pet.owner_id != current_user.id and current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="No tienes acceso al historial de esta mascota")
    
    return db.query(models.MedicalRecord).filter(models.MedicalRecord.pet_id == pet_id).all()

@app.get("/appointments/me", response_model=List[schemas.AppointmentOut])
def list_my_appointments(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    return db.query(models.Appointment).filter(models.Appointment.owner_id == current_user.id).all()

@app.post("/appointments/", response_model=schemas.AppointmentOut)
def create_appointment(
    appointment: schemas.AppointmentCreate, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    # Verificar que la mascota le pertenezca
    pet = db.query(models.Pet).filter(models.Pet.id == appointment.pet_id, models.Pet.owner_id == current_user.id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Mascota no encontrada")
    
    new_appo = models.Appointment(
        **appointment.dict(), 
        owner_id=current_user.id,
        status=models.AppointmentStatus.PENDING
    )
    db.add(new_appo)
    db.commit()
    db.refresh(new_appo)
    return new_appo
