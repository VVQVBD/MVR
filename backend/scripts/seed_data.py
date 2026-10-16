"""Наполнение БД из contracts.json пакета организаторов.

    python -m scripts.seed_data ../data/contracts.json
    python -m scripts.seed_data ../data/contracts.json --as-of 2026-10-16 --force

Создаёт/обновляет 8 компаний-клиентов, договоры и ДС, объекты, субподрядчиков,
графики смен по назначениям из пакета, 11 спорных условий и ссылки на источники.
Пользователей не создаёт — для этого scripts.create_user.
"""
import argparse
import datetime as dt
import sys

from app.db import SessionLocal
from app.services.importer import ImportBlocked, import_contracts, load_file


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", default="../data/contracts.json")
    parser.add_argument("--as-of", type=dt.date.fromisoformat, help="дата расчёта статусов договоров (по умолчанию as_of из файла)")
    parser.add_argument("--force", action="store_true", help="перезагрузить, даже если уже есть отметки смен (они будут удалены)")
    args = parser.parse_args(argv)

    raw = load_file(args.path)
    with SessionLocal() as db:
        try:
            summary = import_contracts(db, raw, as_of=args.as_of, force=args.force)
        except ImportBlocked as e:
            print(e, file=sys.stderr)
            return 1
    print(summary.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
