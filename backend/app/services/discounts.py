"""Скидка клиенту за честную низкую оценку оператора — см. ClientDiscount в app/models.py.

Механика (решение команды): низкая оценка (средний балл ниже порога комментария — уже требует
обоснования, этого достаточно для доверия, отдельной модерации нет) выдаёт клиенту скидку;
потратить её можно только на заявку, которую назначили оператору из нижних
`discount_operator_bottom_share` рейтинга квартала — так оператор получает шанс поднять рейтинг,
а клиент — более низкую цену. Обе стороны в выигрыше, как в исходном предложении участника.
"""
import datetime as dt
from decimal import Decimal
from typing import Optional

from app.config import settings
from app.models import ClientDiscount, OperatorRating
from app.services.operator_rating import rating_needs_comment


def grant_if_low_rating(rating: OperatorRating, client_company_id: Optional[int]) -> Optional[ClientDiscount]:
    """После сохранения `rating` — та же проверка, что уже требует обязательный комментарий
    (хоть один критерий ниже порога): раз комментарий есть, оценка добросовестна, отдельной
    модерации не нужно. Возвращает None, если оценка не низкая или клиент не известен (разовая
    заявка без client_company_id — скидку потом не на что начислить)."""
    if client_company_id is None:
        return None
    if not rating_needs_comment(rating.cleanliness, rating.quality, rating.promptness, rating.courtesy):
        return None
    return ClientDiscount(
        client_company_id=client_company_id,
        pct=settings.client_discount_pct,
        source_rating=rating,
        status="available",
    )


def apply_to_order(discount: ClientDiscount, order) -> None:
    """Фиксирует применение скидки к заявке: цена уменьшается на discount.pct, исходная цена
    сохраняется в order.price_before_discount для прослеживаемости."""
    order.price_before_discount = order.price_net
    order.price_net = (order.price_net * (Decimal(100) - discount.pct) / Decimal(100)).quantize(Decimal("0.01"))
    discount.used_on_order = order
    discount.status = "used"
    discount.used_at = dt.datetime.now(dt.timezone.utc)
