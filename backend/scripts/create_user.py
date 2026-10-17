"""Создать пользователя.

    python -m scripts.create_user boss@icgroup.local <пароль> executive
    python -m scripts.create_user client@modena.local <пароль> client --client modena
    python -m scripts.create_user p23@cleaners.local <пароль> subcontractor --subcontractor P23
    python -m scripts.create_user op047@cleaners.local <пароль> operator --operator-code OP-047
"""
import argparse
import sys
import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models import ROLES, ClientCompany, Operator, Subcontractor, User
from app.security import hash_password


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("email")
    p.add_argument("password")
    p.add_argument("role", choices=ROLES)
    p.add_argument("--client", help="код компании (modena, lira, …) для роли client")
    p.add_argument("--subcontractor", help="код субподрядчика (P23, …) для роли subcontractor")
    p.add_argument("--operator-code", help="табельный код (OP-047, …) для роли operator — см. scripts.create_operator")
    p.add_argument("--auth-user-id", type=uuid.UUID, help="id пользователя в Supabase Auth (для RLS)")
    a = p.parse_args(argv)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == a.email)) or User(email=a.email)
        user.password_hash = hash_password(a.password)
        user.role = a.role
        user.auth_user_id = a.auth_user_id or user.auth_user_id
        user.client_company_id = user.subcontractor_id = user.operator_id = None
        if a.role == "client":
            company = db.scalar(select(ClientCompany).where(ClientCompany.code == a.client))
            if company is None:
                sys.exit(f"Компания {a.client!r} не найдена")
            user.client_company_id = company.id
        if a.role == "subcontractor":
            sub = db.scalar(select(Subcontractor).where(Subcontractor.code == a.subcontractor))
            if sub is None:
                sys.exit(f"Субподрядчик {a.subcontractor!r} не найден")
            user.subcontractor_id = sub.id
        if a.role == "operator":
            operator = db.scalar(select(Operator).where(Operator.code == a.operator_code))
            if operator is None:
                sys.exit(f"Оператор {a.operator_code!r} не найден — сначала scripts.create_operator")
            user.operator_id = operator.id
        db.add(user)
        db.commit()
    print(f"{a.email}: {a.role}")


if __name__ == "__main__":
    main()
