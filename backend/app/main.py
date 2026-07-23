from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, inspect, text
from typing import List
from datetime import date, datetime, timedelta
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

    # Auto-migracion: agregar columnas faltantes
    try:
        mig_db = SessionLocal()
        inspector = inspect(engine)

        def add_column_if_missing(table_name: str, column_name: str, ddl: str):
            if table_name not in inspector.get_table_names():
                return
            columns = [c["name"] for c in inspector.get_columns(table_name)]
            if column_name not in columns:
                mig_db.execute(text(ddl))
                print(f">>> Columna {column_name} agregada a {table_name}")

        # Pets
        add_column_if_missing("pets", "sex", "ALTER TABLE pets ADD COLUMN sex VARCHAR")
        add_column_if_missing("pets", "color", "ALTER TABLE pets ADD COLUMN color VARCHAR")
        add_column_if_missing("pets", "size", "ALTER TABLE pets ADD COLUMN size VARCHAR")
        add_column_if_missing("pets", "allergies", "ALTER TABLE pets ADD COLUMN allergies VARCHAR")
        add_column_if_missing("pets", "conditions", "ALTER TABLE pets ADD COLUMN conditions VARCHAR")
        add_column_if_missing("pets", "microchip", "ALTER TABLE pets ADD COLUMN microchip VARCHAR")
        add_column_if_missing("pets", "microchip", "ALTER TABLE pets ADD COLUMN microchip VARCHAR")
        add_column_if_missing("pets", "status", "ALTER TABLE pets ADD COLUMN status VARCHAR DEFAULT 'active'")

        # Appointments
        add_column_if_missing("appointments", "vet_id", "ALTER TABLE appointments ADD COLUMN vet_id INTEGER")
        add_column_if_missing("appointments", "notes", "ALTER TABLE appointments ADD COLUMN notes VARCHAR")

        # Medical records
        add_column_if_missing("medical_records", "vet_id", "ALTER TABLE medical_records ADD COLUMN vet_id INTEGER")
        add_column_if_missing(
            "medical_records",
            "appointment_id",
            "ALTER TABLE medical_records ADD COLUMN appointment_id INTEGER REFERENCES appointments(id)"
        )

        mig_db.commit()
        mig_db.close()
    except Exception as e:
        try:
            mig_db.close()
        except:
            pass
        print(f">>> Auto-migracion omitida: {e}")

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

@app.post("/auth/register-vet", response_model=schemas.UserOut)
def register_vet(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        if db_user.status == models.UserStatus.REJECTED.value:
            raise HTTPException(status_code=400, detail="Esta cuenta fue rechazada. Contacte al administrador.")
        raise HTTPException(status_code=400, detail="Email ya registrado")

    hashed_pwd = auth.get_password_hash(user.password)
    new_user = models.User(
        email=user.email,
        hashed_password=hashed_pwd,
        full_name=user.full_name,
        phone=user.phone,
        role=models.UserRole.VET.value,
        status=models.UserStatus.PENDING.value
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

@app.patch("/admin/users/{user_id}/deactivate", response_model=schemas.UserOut)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.role in [models.UserRole.ADMIN.value, models.UserRole.SUPERUSER.value]:
        raise HTTPException(status_code=400, detail="No puedes desactivar a un administrador")

    user.status = models.UserStatus.INACTIVE.value

    # Cascada: si es owner, desactivar sus mascotas y cancelar citas pendientes de esas mascotas
    if user.role == models.UserRole.CLIENT.value:
        pets = db.query(models.Pet).filter(models.Pet.owner_id == user.id).all()
        pet_ids = [p.id for p in pets]

        for pet in pets:
            pet.status = models.PetStatus.INACTIVE.value

        if pet_ids:
            db.query(models.Appointment).filter(
                models.Appointment.pet_id.in_(pet_ids),
                models.Appointment.status == models.AppointmentStatus.PENDING.value
            ).update({"status": models.AppointmentStatus.CANCELLED.value}, synchronize_session=False)

    db.commit()
    db.refresh(user)
    return user


@app.patch("/admin/users/{user_id}/reactivate", response_model=schemas.UserOut)
def reactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.status = models.UserStatus.ACTIVE.value
    db.commit()
    db.refresh(user)
    return user

@app.get("/admin/vets", response_model=List[schemas.VeterinaryOut])
def get_all_vets(
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    try:
        auth.check_admin(admin)
        vets = db.query(models.Veterinary).all()
        return [
            schemas.VeterinaryOut(
                id=v.id, owner_user_id=v.owner_user_id, name=v.name, address=v.address,
                phone=v.phone, specialties=v.specialties, description=v.description,
                working_hours=v.working_hours, photo_url=v.photo_url, status=v.status,
                owner_name=v.owner.full_name if v.owner else None
            )
            for v in vets
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener veterinarias: {str(e)}")


@app.get("/admin/vets/pending", response_model=List[schemas.UserOut])
def get_pending_vets(
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    try:
        auth.check_admin(admin)
        return db.query(models.User).filter(
            models.User.role == models.UserRole.VET,
            models.User.status == models.UserStatus.PENDING
        ).all()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener veterinarias pendientes: {str(e)}")


@app.patch("/admin/vets/{vet_id}/deactivate", response_model=schemas.VeterinaryOut)
def deactivate_vet(
    vet_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    vet = db.query(models.Veterinary).filter(models.Veterinary.id == vet_id).first()
    if not vet:
        raise HTTPException(status_code=404, detail="Veterinaria no encontrada")

    vet.status = models.VeterinaryStatus.INACTIVE.value

    # Cascada: cancelar citas pendientes de esta vet
    db.query(models.Appointment).filter(
        models.Appointment.vet_id == vet.id,
        models.Appointment.status == models.AppointmentStatus.PENDING.value
    ).update({"status": models.AppointmentStatus.CANCELLED.value}, synchronize_session=False)

    db.commit()
    db.refresh(vet)
    return schemas.VeterinaryOut(
        id=vet.id, owner_user_id=vet.owner_user_id, name=vet.name, address=vet.address,
        phone=vet.phone, specialties=vet.specialties, description=vet.description,
        working_hours=vet.working_hours, photo_url=vet.photo_url, status=vet.status,
        owner_name=vet.owner.full_name if vet.owner else None
    )


@app.patch("/admin/vets/{vet_id}/reactivate", response_model=schemas.VeterinaryOut)
def reactivate_vet(
    vet_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    auth.check_admin(admin)
    vet = db.query(models.Veterinary).filter(models.Veterinary.id == vet_id).first()
    if not vet:
        raise HTTPException(status_code=404, detail="Veterinaria no encontrada")

    vet.status = models.VeterinaryStatus.ACTIVE.value
    db.commit()
    db.refresh(vet)
    return schemas.VeterinaryOut(
        id=vet.id, owner_user_id=vet.owner_user_id, name=vet.name, address=vet.address,
        phone=vet.phone, specialties=vet.specialties, description=vet.description,
        working_hours=vet.working_hours, photo_url=vet.photo_url, status=vet.status,
        owner_name=vet.owner.full_name if vet.owner else None
    )

@app.get("/admin/users/{user_id}", response_model=schemas.UserDetail)
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    try:
        auth.check_admin(admin)
        user = db.query(models.User).options(joinedload(models.User.pets)).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        pets_out = []
        for p in user.pets:
            pets_out.append(schemas.PetOut(
                id=p.id, owner_id=p.owner_id,
                name=p.name or "", species=p.species or "", breed=p.breed or "",
                birth_date=p.birth_date or "", weight=p.weight or 0.0,
                photo_url=p.photo_url,
                sex=p.sex, color=p.color, size=p.size,
                allergies=p.allergies, conditions=p.conditions,
                microchip=p.microchip, status=p.status or "active"
            ))
        return schemas.UserDetail(
            id=user.id, email=user.email, full_name=user.full_name,
            phone=user.phone, role=user.role, status=user.status,
            pets=pets_out
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener usuario: {str(e)}")

@app.get("/admin/pets", response_model=List[schemas.PetWithOwner])
def get_all_pets(
    search: str = "",
    owner_id: int = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_user)
):
    try:
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
                name=p.name or "",
                species=p.species or "",
                breed=p.breed or "",
                birth_date=p.birth_date or "",
                weight=p.weight or 0.0,
                photo_url=p.photo_url,
                owner_name=p.owner.full_name if p.owner else None
            )
            for p in pets
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener mascotas: {str(e)}")

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
        ).scalar(),
        total_vets_active=db.query(func.count(models.Veterinary.id)).filter(
            models.Veterinary.status == models.VeterinaryStatus.ACTIVE.value
        ).scalar(),
        confirmed_appointments=db.query(func.count(models.Appointment.id)).filter(
            models.Appointment.status == models.AppointmentStatus.CONFIRMED
        ).scalar(),
        completed_appointments=db.query(func.count(models.Appointment.id)).filter(
            models.Appointment.status == models.AppointmentStatus.COMPLETED
        ).scalar(),
        cancelled_appointments=db.query(func.count(models.Appointment.id)).filter(
            models.Appointment.status == models.AppointmentStatus.CANCELLED
        ).scalar()
    )

@app.get("/admin/appointments", response_model=List[schemas.AppointmentOut])
def get_all_appointments(
    db: Session = Depends(get_db), 
    admin: models.User = Depends(auth.get_current_user)
):
    try:
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
                reason=a.reason or "", status=a.status,
                vet_id=a.vet_id, notes=a.notes,
                owner_name=owner.full_name if owner else None,
                pet_name=pet.name if pet else None,
                has_record=has_record
            ))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener citas: {str(e)}")

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
        vet_id=appointment.vet_id, notes=appointment.notes,
        owner_name=owner.full_name if owner else None,
        pet_name=pet.name if pet else None
    )
    return result

# --- VETS (búsqueda para owners) ---

@app.get("/vets/search", response_model=List[schemas.VeterinaryOut])
def search_vets(
    q: str = "",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    query = db.query(models.Veterinary).filter(
        models.Veterinary.status == models.VeterinaryStatus.ACTIVE.value
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            (models.Veterinary.name.ilike(like)) |
            (models.Veterinary.specialties.ilike(like)) |
            (models.Veterinary.address.ilike(like))
        )
    vets = query.all()
    return [
        schemas.VeterinaryOut(
            id=v.id, owner_user_id=v.owner_user_id, name=v.name, address=v.address,
            phone=v.phone, specialties=v.specialties, description=v.description,
            working_hours=v.working_hours, photo_url=v.photo_url, status=v.status,
            owner_name=v.owner.full_name if v.owner else None
        )
        for v in vets
    ]


@app.get("/vets/{vet_id}", response_model=schemas.VeterinaryOut)
def get_vet_detail(
    vet_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    vet = db.query(models.Veterinary).filter(models.Veterinary.id == vet_id).first()
    if not vet:
        raise HTTPException(status_code=404, detail="Veterinaria no encontrada")
    return schemas.VeterinaryOut(
        id=vet.id, owner_user_id=vet.owner_user_id, name=vet.name, address=vet.address,
        phone=vet.phone, specialties=vet.specialties, description=vet.description,
        working_hours=vet.working_hours, photo_url=vet.photo_url, status=vet.status,
        owner_name=vet.owner.full_name if vet.owner else None
    )



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
    try:
        auth.check_active(current_user)
        return db.query(models.Pet).filter(models.Pet.owner_id == current_user.id).all()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener mascotas: {str(e)}")

@app.get("/pets/{pet_id}", response_model=schemas.PetOut)
def get_pet(
    pet_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Mascota no encontrada")
    if pet.owner_id != current_user.id and current_user.role not in [
        models.UserRole.ADMIN.value, models.UserRole.SUPERUSER.value
    ]:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta mascota")
    return pet


@app.patch("/pets/{pet_id}", response_model=schemas.PetOut)
def update_pet(
    pet_id: int,
    update: schemas.PetUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Mascota no encontrada")
    if pet.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Solo puedes editar tus propias mascotas")

    update_data = update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pet, field, value)

    db.commit()
    db.refresh(pet)
    return pet

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
    try:
        auth.check_active(current_user)
        appointments = db.query(models.Appointment).filter(models.Appointment.owner_id == current_user.id).all()
        result = []
        for a in appointments:
            pet = a.pet
            result.append(schemas.AppointmentOut(
                id=a.id, pet_id=a.pet_id, owner_id=a.owner_id, date_time=a.date_time,
                reason=a.reason or "", status=a.status,
                vet_id=a.vet_id, notes=a.notes,
                owner_name=current_user.full_name,
                pet_name=pet.name if pet else None
            ))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener citas: {str(e)}")

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

    # Verificar que el vet exista y esté activo
    vet = db.query(models.Veterinary).filter(models.Veterinary.id == appointment.vet_id).first()
    if not vet:
        raise HTTPException(status_code=404, detail="Veterinaria no encontrada")
    if vet.status != models.VeterinaryStatus.ACTIVE.value:
        raise HTTPException(status_code=400, detail="Esta veterinaria no está disponible actualmente")

    # Validar fecha: no en el pasado, no más de 30 días en el futuro
    now = datetime.utcnow()
    if appointment.date_time < now:
        raise HTTPException(status_code=400, detail="No puedes agendar una cita en el pasado")
    if appointment.date_time > now + timedelta(days=30):
        raise HTTPException(status_code=400, detail="Las citas solo se pueden agendar hasta 30 días en el futuro")

    new_appo = models.Appointment(
        **appointment.dict(), 
        owner_id=current_user.id,
        status=models.AppointmentStatus.PENDING
    )
    db.add(new_appo)
    db.commit()
    db.refresh(new_appo)
    return _appointment_to_out(new_appo)


def get_my_vet_business(db: Session, current_user: models.User) -> models.Veterinary:
    vet = db.query(models.Veterinary).filter(
        models.Veterinary.owner_user_id == current_user.id
    ).first()
    if not vet:
        raise HTTPException(status_code=404, detail="No tienes un negocio de veterinaria registrado")
    return vet


# --- VET ENDPOINTS ---

@app.get("/vet/business", response_model=schemas.VeterinaryOut)
def get_my_business(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    auth.check_vet(current_user)
    vet = get_my_vet_business(db, current_user)
    return schemas.VeterinaryOut(
        id=vet.id, owner_user_id=vet.owner_user_id, name=vet.name, address=vet.address,
        phone=vet.phone, specialties=vet.specialties, description=vet.description,
        working_hours=vet.working_hours, photo_url=vet.photo_url, status=vet.status,
        owner_name=current_user.full_name
    )


@app.post("/vet/business", response_model=schemas.VeterinaryOut)
def create_my_business(
    business: schemas.VeterinaryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    auth.check_vet(current_user)

    existing = db.query(models.Veterinary).filter(
        models.Veterinary.owner_user_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ya tienes un negocio registrado")

    new_vet = models.Veterinary(
        **business.dict(),
        owner_user_id=current_user.id
    )
    db.add(new_vet)
    db.commit()
    db.refresh(new_vet)
    return schemas.VeterinaryOut(
        id=new_vet.id, owner_user_id=new_vet.owner_user_id, name=new_vet.name,
        address=new_vet.address, phone=new_vet.phone, specialties=new_vet.specialties,
        description=new_vet.description, working_hours=new_vet.working_hours,
        photo_url=new_vet.photo_url, status=new_vet.status,
        owner_name=current_user.full_name
    )


@app.patch("/vet/business", response_model=schemas.VeterinaryOut)
def update_my_business(
    update: schemas.VeterinaryUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    auth.check_vet(current_user)
    vet = get_my_vet_business(db, current_user)

    update_data = update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(vet, field, value)

    db.commit()
    db.refresh(vet)
    return schemas.VeterinaryOut(
        id=vet.id, owner_user_id=vet.owner_user_id, name=vet.name, address=vet.address,
        phone=vet.phone, specialties=vet.specialties, description=vet.description,
        working_hours=vet.working_hours, photo_url=vet.photo_url, status=vet.status,
        owner_name=current_user.full_name
    )

@app.get("/vet/appointments", response_model=List[schemas.AppointmentOut])
def get_my_vet_appointments(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    auth.check_vet(current_user)
    vet = get_my_vet_business(db, current_user)

    appointments = db.query(models.Appointment).filter(
        models.Appointment.vet_id == vet.id
    ).all()

    result = []
    for a in appointments:
        owner = a.owner
        pet = a.pet
        has_record = db.query(models.MedicalRecord).filter(
            models.MedicalRecord.appointment_id == a.id
        ).first() is not None
        result.append(schemas.AppointmentOut(
            id=a.id, pet_id=a.pet_id, owner_id=a.owner_id, date_time=a.date_time,
            reason=a.reason, status=a.status, vet_id=a.vet_id, notes=a.notes,
            owner_name=owner.full_name if owner else None,
            pet_name=pet.name if pet else None,
            has_record=has_record
        ))
    return result


def _get_owned_appointment(db: Session, appointment_id: int, vet: models.Veterinary) -> models.Appointment:
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if appointment.vet_id != vet.id:
        raise HTTPException(status_code=403, detail="Esta cita no pertenece a tu negocio")
    return appointment


def _appointment_to_out(a: models.Appointment) -> schemas.AppointmentOut:
    owner = a.owner
    pet = a.pet
    return schemas.AppointmentOut(
        id=a.id, pet_id=a.pet_id, owner_id=a.owner_id, date_time=a.date_time,
        reason=a.reason, status=a.status, vet_id=a.vet_id, notes=a.notes,
        owner_name=owner.full_name if owner else None,
        pet_name=pet.name if pet else None
    )


@app.patch("/vet/appointments/{appointment_id}/accept", response_model=schemas.AppointmentOut)
def accept_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    auth.check_vet(current_user)
    vet = get_my_vet_business(db, current_user)
    appointment = _get_owned_appointment(db, appointment_id, vet)

    if appointment.status != models.AppointmentStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Solo se pueden aceptar citas en estado pendiente")

    owner = appointment.owner
    if not owner or owner.status != models.UserStatus.ACTIVE.value:
        raise HTTPException(status_code=400, detail="No puedes aceptar una cita de un usuario inactivo")

    appointment.status = models.AppointmentStatus.CONFIRMED.value
    db.commit()
    db.refresh(appointment)
    return _appointment_to_out(appointment)


@app.patch("/vet/appointments/{appointment_id}/reject", response_model=schemas.AppointmentOut)
def reject_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    auth.check_vet(current_user)
    vet = get_my_vet_business(db, current_user)
    appointment = _get_owned_appointment(db, appointment_id, vet)

    if appointment.status != models.AppointmentStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Solo se pueden rechazar citas en estado pendiente")

    appointment.status = models.AppointmentStatus.CANCELLED.value
    db.commit()
    db.refresh(appointment)
    return _appointment_to_out(appointment)


@app.patch("/vet/appointments/{appointment_id}/complete", response_model=schemas.AppointmentOut)
def complete_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    auth.check_vet(current_user)
    vet = get_my_vet_business(db, current_user)
    appointment = _get_owned_appointment(db, appointment_id, vet)

    if appointment.status != models.AppointmentStatus.CONFIRMED.value:
        raise HTTPException(status_code=400, detail="Solo se pueden completar citas confirmadas")

    appointment.status = models.AppointmentStatus.COMPLETED.value
    db.commit()
    db.refresh(appointment)
    return _appointment_to_out(appointment)

@app.get("/vet/patients", response_model=List[schemas.PetWithOwner])
def get_my_patients(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    auth.check_vet(current_user)
    vet = get_my_vet_business(db, current_user)

    pets = db.query(models.Pet).join(
        models.MedicalRecord, models.MedicalRecord.pet_id == models.Pet.id
    ).filter(
        models.MedicalRecord.vet_id == vet.id
    ).distinct().all()

    return [
        schemas.PetWithOwner(
            id=p.id, owner_id=p.owner_id, name=p.name, species=p.species,
            breed=p.breed, birth_date=p.birth_date, weight=p.weight,
            photo_url=p.photo_url, owner_name=p.owner.full_name if p.owner else None,
            sex=p.sex, color=p.color, size=p.size, allergies=p.allergies,
            conditions=p.conditions, microchip=p.microchip
        )
        for p in pets
    ]

@app.post("/vet/medical-records", response_model=schemas.MedicalRecordOut)
def create_medical_record_as_vet(
    record: schemas.VetMedicalRecordCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    auth.check_active(current_user)
    auth.check_vet(current_user)
    vet = get_my_vet_business(db, current_user)

    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == record.appointment_id
    ).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if appointment.vet_id != vet.id:
        raise HTTPException(status_code=403, detail="Esta cita no pertenece a tu negocio")
    if appointment.status != models.AppointmentStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Solo puedes crear historial de citas completadas")

    existing_record = db.query(models.MedicalRecord).filter(
        models.MedicalRecord.appointment_id == appointment.id
    ).first()
    if existing_record:
        raise HTTPException(status_code=400, detail="Esta cita ya tiene un historial médico registrado")

    new_record = models.MedicalRecord(
        pet_id=appointment.pet_id,
        vet_id=vet.id,
        appointment_id=appointment.id,
        diagnosis=record.diagnosis,
        treatment=record.treatment,
        notes=record.notes,
        date=datetime.utcnow()
    )
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return new_record