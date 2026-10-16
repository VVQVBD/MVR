"""Акты субподрядчиков из файла факта: python -m scripts.import_actuals ../data/05_Факт_сентябрь_2026.xlsx --year 2026

Запускать после seed_data.py: строки актов сопоставляются объектам из базы.
"""
import argparse
import sys

from app.db import SessionLocal
from app.services.actuals import import_actuals


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", nargs="?", default="../data/05_Факт_сентябрь_2026.xlsx")
    p.add_argument("--year", type=int, default=2026)
    a = p.parse_args(argv)
    with SessionLocal() as db:
        s = import_actuals(db, a.path, a.year)
    print(f"актов: {s.acts}, строк: {s.lines}, сопоставлено объектам: {s.matched}, сумма: {s.total_amount} ₸")
    for w in s.warnings:
        print("!", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
