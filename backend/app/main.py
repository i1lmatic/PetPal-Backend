from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List
from datetime import timedelta, date, datetime
import os

from . import models, schemas, auth, database
from .database import engine, get_db, SessionLocal

@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    try:
        db = SessionLocal()
        try:
            existing = db.query(models.User).filter(models.User.role == models.UserRole.ADMIN).first()
            if not existing:
                admin_user = models.User(
                    email=os.environ.get("ADMIN_EMAIL", "admin@petpal.com"),
                    hashed_password=auth.get_password_hash(os.environ.get("ADMIN_PASSWORD", "admin123")),
                    full_name="Administrador",
                    phone="000000000",
                    role=models.UserRole.ADMIN,
                    status=models.UserStatus.ACTIVE
                )
                db.add(admin_user)
                db.commit()
                print(">>> Admin default creado")
        except Exception as e:
            db.rollback()
            print(f">>> Seed admin omitido (posible BD ya poblada): {e}")
        finally:
            db.close()
    except Exception as e:
        print(f">>> No se pudo crear sesión de DB para seed: {e}")
    yield

app = FastAPI(title="PetPal API", lifespan=lifespan)

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

# --- AUTH ENDPOINTS ---

@app.post("/auth/register", response_model=schemas.UserOut)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        if db_user.status == models.UserStatus.REJECTED:
            raise HTTPException(status_code=400, detail="Esta cuenta fue rechazada. Contacte al administrador.")
        raise HTTPException(status_code=400, detail="Email ya registrado")
    
    hashed_pwd = auth.get_password_hash(user.password)
    existing_admin = db.query(models.User).filter(models.User.role == models.UserRole.ADMIN).first()
    is_first_user = existing_admin is None
    new_user = models.User(
        email=user.email,
        hashed_password=hashed_pwd,
        full_name=user.full_name,
        phone=user.phone,
        role=models.UserRole.ADMIN if is_first_user else models.UserRole.CLIENT,
        status=models.UserStatus.ACTIVE if is_first_user else models.UserStatus.PENDING
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

@app.patch("/users/me", response_model=schemas.UserOut)
def update_my_profile(
    update: schemas.UserUpdateProfile,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if update.full_name is not None:
        current_user.full_name = update.full_name
    if update.phone is not None:
        current_user.phone = update.phone
    db.commit()
    db.refresh(current_user)
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

@app.delete("/admin/users/{user_id}/reject", response_model=schemas.UserOut)
def reject_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.status = models.UserStatus.REJECTED
    db.commit()
    db.refresh(user)
    return user

@app.get("/admin/users/active", response_model=List[schemas.UserOut])
def get_active_users(
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    return db.query(models.User).filter(models.User.status == models.UserStatus.ACTIVE).all()

@app.get("/admin/users/{user_id}", response_model=schemas.UserDetail)
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    user = db.query(models.User).options(joinedload(models.User.pets)).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

@app.get("/admin/pets", response_model=List[schemas.PetWithOwner])
def get_all_pets(
    search: str = "",
    owner_id: int = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    query = db.query(models.Pet).join(models.User)
    if search:
        query = query.filter(models.Pet.name.ilike(f"%{search}%"))
    if owner_id is not None:
        query = query.filter(models.Pet.owner_id == owner_id)
    pets = query.all()
    return [
        schemas.PetWithOwner(
            id=p.id,
            owner_id=p.owner_id,
            name=p.name,
            species=p.species,
            breed=p.breed,
            birth_date=p.birth_date,
            weight=p.weight,
            photo_url=p.photo_url,
            owner_name=p.owner.full_name if p.owner else None
        )
        for p in pets
    ]

@app.get("/admin/dashboard/stats", response_model=schemas.DashboardStats)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    today = date.today()
    return schemas.DashboardStats(
        total_users=db.query(func.count(models.User.id)).filter(models.User.status == models.UserStatus.ACTIVE).scalar(),
        total_pets=db.query(func.count(models.Pet.id)).scalar(),
        total_appointments=db.query(func.count(models.Appointment.id)).scalar(),
        appointments_today=db.query(func.count(models.Appointment.id)).filter(
            func.date(models.Appointment.date_time) == today
        ).scalar(),
        pending_appointments=db.query(func.count(models.Appointment.id)).filter(
            models.Appointment.status == models.AppointmentStatus.PENDING
        ).scalar(),
        pending_users=db.query(func.count(models.User.id)).filter(
            models.User.status == models.UserStatus.PENDING
        ).scalar()
    )

@app.get("/admin/appointments", response_model=List[schemas.AppointmentOut])
def get_all_appointments(
    db: Session = Depends(get_db), 
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    appointments = db.query(models.Appointment).all()
    result = []
    for a in appointments:
        owner = a.owner
        pet = a.pet
        has_record = db.query(models.MedicalRecord).filter(
            models.MedicalRecord.appointment_id == a.id
        ).first() is not None
        result.append(schemas.AppointmentOut(
            id=a.id, pet_id=a.pet_id, owner_id=a.owner_id, date_time=a.date_time,
            reason=a.reason, status=a.status,
            owner_name=owner.full_name if owner else None,
            pet_name=pet.name if pet else None,
            has_record=has_record
        ))
    return result

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
        pet_id=record.pet_id,
        diagnosis=record.diagnosis,
        treatment=record.treatment,
        notes=record.notes,
        date=datetime.utcnow(),
        appointment_id=record.appointment_id
    )
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return new_record

@app.patch("/admin/appointments/{appointment_id}/status", response_model=schemas.AppointmentOut)
def update_appointment_status(
    appointment_id: int,
    update: schemas.AppointmentUpdateStatus,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    new_status = update.status
    allowed = [
        models.AppointmentStatus.CONFIRMED,
        models.AppointmentStatus.CANCELLED,
        models.AppointmentStatus.COMPLETED
    ]
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"Estado invalido. Permitidos: {[s.value for s in allowed]}")
    appointment.status = new_status
    db.commit()
    db.refresh(appointment)
    owner = appointment.owner
    pet = appointment.pet
    result = schemas.AppointmentOut(
        id=appointment.id, pet_id=appointment.pet_id, owner_id=appointment.owner_id,
        date_time=appointment.date_time, reason=appointment.reason, status=appointment.status,
        owner_name=owner.full_name if owner else None,
        pet_name=pet.name if pet else None
    )
    return result

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
    appointments = db.query(models.Appointment).filter(models.Appointment.owner_id == current_user.id).all()
    result = []
    for a in appointments:
        pet = a.pet
        result.append(schemas.AppointmentOut(
            id=a.id, pet_id=a.pet_id, owner_id=a.owner_id, date_time=a.date_time,
            reason=a.reason, status=a.status,
            owner_name=current_user.full_name,
            pet_name=pet.name if pet else None
        ))
    return result

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
    pet = new_appo.pet
    return schemas.AppointmentOut(
        id=new_appo.id, pet_id=new_appo.pet_id, owner_id=new_appo.owner_id,
        date_time=new_appo.date_time, reason=new_appo.reason, status=new_appo.status,
        owner_name=current_user.full_name,
        pet_name=pet.name if pet else None
    )
