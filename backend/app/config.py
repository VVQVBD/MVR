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
    # Claude API для разбора текста договоров.
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
    claude_effort: str = os.getenv("CLAUDE_EFFORT", "medium")
    # Допуск при сверке сумм, KZT.
    money_tolerance: Decimal = Decimal(os.getenv("MONEY_TOLERANCE", "0.01"))

    # Пилот рейтинга операторов — см. docs/OPERATOR_RATING_PROPOSAL.md, формула (вариант 2).
    # Баллы лояльности за отработанный час смены (status done=1.0, partial=0.5).
    operator_points_per_hour: int = int(os.getenv("OPERATOR_POINTS_PER_HOUR", "10"))
    # Надбавка/штраф за оценку клиента: (средний балл 1–10 минус середина 5) × это число.
    operator_points_per_rating_unit: int = int(os.getenv("OPERATOR_POINTS_PER_RATING_UNIT", "20"))
    # Оценка ниже этого балла по любому критерию требует обязательного комментария.
    operator_rating_comment_threshold: int = int(os.getenv("OPERATOR_RATING_COMMENT_THRESHOLD", "6"))
    # Премия по месту в рейтинге за квартал: верхние N% участников получают фиксированную сумму, KZT.
    # Доли идут по возрастанию без перекрытия: первая строка — самый узкий топ.
    operator_bonus_tiers: List[tuple] = field(
        default_factory=lambda: [
            (Decimal("0.10"), Decimal(os.getenv("OPERATOR_BONUS_TOP", "50000"))),
            (Decimal("0.30"), Decimal(os.getenv("OPERATOR_BONUS_HIGH", "25000"))),
            (Decimal("0.70"), Decimal(os.getenv("OPERATOR_BONUS_MID", "10000"))),
        ]
    )
    # Баллы за выполненную разовую заявку — по площади, как shift_base, без отдельной ставки за час.
    order_points_per_m2: Decimal = Decimal(os.getenv("ORDER_POINTS_PER_M2", "0.05"))

    # Разовые заявки на уборку (CleaningOrder) — пилотные ставки, в пакете организаторов цен на
    # разовые заявки нет. ₸ за м², без НДС, по уровню качества.
    order_quality_rates: dict = field(
        default_factory=lambda: {
            "surface": Decimal(os.getenv("ORDER_RATE_SURFACE", "150")),
            "standard": Decimal(os.getenv("ORDER_RATE_STANDARD", "220")),
            "general": Decimal(os.getenv("ORDER_RATE_GENERAL", "320")),
        }
    )
    # Куда класть фото после уборки — путь относительно backend/. В проде — объектное хранилище.
    order_photos_dir: str = os.getenv("ORDER_PHOTOS_DIR", "storage/order-photos")
    order_photo_max_bytes: int = int(os.getenv("ORDER_PHOTO_MAX_BYTES", str(8 * 1024 * 1024)))

    # Скидка клиенту за честную низкую оценку (см. ClientDiscount в app/models.py) — пилотное
    # значение, фиксированный процент, как премия операторам.
    client_discount_pct: Decimal = Decimal(os.getenv("CLIENT_DISCOUNT_PCT", "15"))
    # Доля снизу рейтинга квартала, которой можно закрыть скидочную заявку (та же граница,
    # что у «топ-30% выбирает район» сверху — симметрично).
    discount_operator_bottom_share: Decimal = Decimal(os.getenv("DISCOUNT_OPERATOR_BOTTOM_SHARE", "0.30"))


settings = Settings()
