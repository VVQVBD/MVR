"""Демо-режим для показа RBAC: вход по роли без пароля.

Включается только переменной окружения DEMO_MODE=1 — в проде эндпоинт отвечает 404.
Демо-пользователи создаются scripts.create_demo_users и не имеют пароля (вход только этим путём).
"""
import os
from typing import Dict, Optional, Tuple

# роль → (email, код компании для client, код субподрядчика для subcontractor)
DEMO_USERS: Dict[str, Tuple[str, Optional[str], Optional[str]]] = {
    "executive": ("demo-executive@icgroup.demo", None, None),
    "manager": ("demo-manager@icgroup.demo", None, None),
    "client": ("demo-client-modena@icgroup.demo", "modena", None),
    "subcontractor": ("demo-subcontractor-p23@icgroup.demo", None, "P23"),
}


def demo_enabled() -> bool:
    return os.getenv("DEMO_MODE") == "1"
