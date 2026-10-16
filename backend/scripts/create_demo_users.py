"""Демо-пользователи для переключателя ролей: python -m scripts.create_demo_users

Клиент — ТОО «Модена Ритейл KZ», субподрядчик — P23 ИП «Шанырак Клин». Пароля нет:
войти можно только через POST /auth/demo-token при DEMO_MODE=1.
"""
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.demo import DEMO_USERS
from app.models import ClientCompany, Subcontractor, User


def main() -> int:
    with SessionLocal() as db:
        for role, (email, company_code, sub_code) in DEMO_USERS.items():
            user = db.scalar(select(User).where(User.email == email)) or User(email=email)
            user.role, user.password_hash = role, None
            user.client_company_id = user.subcontractor_id = None
            if company_code:
                company = db.scalar(select(ClientCompany).where(ClientCompany.code == company_code))
                if company is None:
                    print(f"Нет компании {company_code} — сначала seed_data", file=sys.stderr)
                    return 1
                user.client_company_id = company.id
            if sub_code:
                sub = db.scalar(select(Subcontractor).where(Subcontractor.code == sub_code))
                if sub is None:
                    print(f"Нет субподрядчика {sub_code} — сначала seed_data", file=sys.stderr)
                    return 1
                user.subcontractor_id = sub.id
            db.add(user)
            print(f"{role}: {email}")
        db.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
