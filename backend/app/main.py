from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, clients, disputes, operations, v1

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


@app.get("/health", tags=["service"])
def health():
    return {"status": "ok"}
