import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from backend.app.database import SessionLocal
from backend.app.models import User, UserRole, UserStatus

db = SessionLocal()
try:
    users = db.query(User).filter(
        User.role == UserRole.CLIENT.value,
        User.status == UserStatus.PENDING.value
    ).all()
    for u in users:
        u.status = UserStatus.ACTIVE.value
        print(f"Activado: {u.full_name} ({u.email})")
    db.commit()
    print(f"\n{len(users)} usuarios activados")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
