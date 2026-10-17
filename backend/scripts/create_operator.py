"""Завести оператора (пилот рейтинга): python -m scripts.create_operator OP-047 P23 "Оператор А15"

Выполнять после seed_data.py (нужны субподрядчики из contracts.json). Логин для оператора —
отдельно: python -m scripts.create_user op047@... <пароль> operator --operator-code OP-047
"""
import argparse
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Operator, Subcontractor


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("code", help="табельный код, напр. OP-047")
    p.add_argument("subcontractor", help="код субподрядчика, напр. P23")
    p.add_argument("display_name", nargs="?", default=None)
    a = p.parse_args(argv)

    with SessionLocal() as db:
        sub = db.scalar(select(Subcontractor).where(Subcontractor.code == a.subcontractor))
        if sub is None:
            sys.exit(f"Субподрядчик {a.subcontractor!r} не найден — сначала scripts.seed_data")
        operator = db.scalar(select(Operator).where(Operator.code == a.code)) or Operator(code=a.code)
        operator.subcontractor_id = sub.id
        operator.display_name = a.display_name
        db.add(operator)
        db.commit()
        print(f"{operator.code}: субподрядчик {sub.code}, id={operator.id}")


if __name__ == "__main__":
    main()
