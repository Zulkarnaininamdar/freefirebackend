import os

from sqlalchemy.orm import Session

from .auth import hash_password
from .models import Admin


def seed_admin(db: Session) -> None:
    admin_id = os.getenv("ADMIN_ID", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "changeme123")

    admin = db.query(Admin).filter(Admin.username == admin_id).first()
    if admin is None:
        # Remove any other stale admin rows so there's always exactly one account
        db.query(Admin).delete()
        admin = Admin(username=admin_id, password_hash=hash_password(admin_password))
        db.add(admin)
    else:
        admin.password_hash = hash_password(admin_password)
    db.commit()
