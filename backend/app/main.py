from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import auth, clients, disputes, operations, operators, orders, v1

app = FastAPI(
    title="IC Group — договоры и спорные условия",
    version="0.1.0",
    description="Клиенты, договоры и ДС, объекты, субподрядчики, графики смен, акты, реестр disputed_conditions и автопроверки.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(disputes.router)
app.include_router(operations.router)
app.include_router(v1.router)
app.include_router(operators.router)
app.include_router(orders.router)

# Фото после уборки — пилот: раздаём как статику по случайному имени файла (см. routers/orders.py).
# В проде — переезд на S3-совместимое хранилище с подписанными URL, без смены схемы API.
_photos_dir = Path(__file__).resolve().parents[1] / settings.order_photos_dir
_photos_dir.mkdir(parents=True, exist_ok=True)
app.mount(f"/{settings.order_photos_dir}", StaticFiles(directory=_photos_dir), name="order-photos")


@app.get("/health", tags=["service"])
def health():
    return {"status": "ok"}
