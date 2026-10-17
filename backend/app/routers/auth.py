from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.demo import DEMO_USERS, demo_enabled
from app.models import User
from app.schemas import Token, UserCreate, UserOut
from app.security import create_access_token, executive, get_current_user, hash_password, staff, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username))
    if user is None or not user.password_hash or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")
    return Token(access_token=create_access_token(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=List[UserOut], dependencies=[Depends(staff)])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.email)).all()


@router.post("/users", response_model=UserOut, status_code=201, dependencies=[Depends(executive)])
def create_user(body: UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Пользователь уже существует")
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        client_company_id=body.client_company_id if body.role == "client" else None,
        subcontractor_id=body.subcontractor_id if body.role == "subcontractor" else None,
        operator_id=body.operator_id if body.role == "operator" else None,
    )
    db.add(user)
    db.commit()
    return user


class DemoTokenIn(BaseModel):
    role: Literal["executive", "manager", "client", "subcontractor"]


@router.post("/demo-token", response_model=Token, include_in_schema=False)
def demo_token(body: DemoTokenIn, db: Session = Depends(get_db)):
    """Только при DEMO_MODE=1: токен демо-пользователя роли — для переключателя ролей на фронте."""
    if not demo_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not Found")
    email = DEMO_USERS[body.role][0]
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Демо-пользователи не созданы: python -m scripts.create_demo_users")
    return Token(access_token=create_access_token(user))
