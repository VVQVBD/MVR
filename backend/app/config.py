"""Настройки приложения из переменных окружения."""
import datetime as dt
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List


def _list(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # SQLite по умолчанию; для Supabase — строка подключения Postgres:
    # postgresql+psycopg://postgres:<pwd>@db.<project>.supabase.co:5432/postgres
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./icgroup.db")
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-only-secret-change-me-in-production-32b")
    jwt_ttl_minutes: int = int(os.getenv("JWT_TTL_MINUTES", "480"))
    cors_origins: List[str] = field(
        default_factory=lambda: _list(os.getenv("CORS_ORIGINS", "http://localhost:3000"))
    )
    # Новый Налоговый кодекс РК: ставка НДС 16% с 01.01.2026.
    vat_new_rate: Decimal = Decimal(os.getenv("VAT_NEW_RATE", "16"))
    vat_old_rate: Decimal = Decimal(os.getenv("VAT_OLD_RATE", "12"))
    vat_change_date: dt.date = dt.date.fromisoformat(os.getenv("VAT_CHANGE_DATE", "2026-01-01"))
    # За сколько дней предупреждать об окончании срока без автопролонгации.
    expiring_days: int = int(os.getenv("EXPIRING_DAYS", "90"))
    # Тарифы по ставке за м² в документах округлены до 100 тг: такие строки не считаются ошибкой.
    per_m2_rounding: Decimal = Decimal(os.getenv("PER_M2_ROUNDING", "100"))
    # Допуск при сверке сумм, KZT.
    money_tolerance: Decimal = Decimal(os.getenv("MONEY_TOLERANCE", "0.01"))


settings = Settings()
