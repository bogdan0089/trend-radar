from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user, is_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService

router_auth = APIRouter(prefix="/api/auth", tags=["auth"])


@router_auth.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_db)) -> TokenResponse:
    token = AuthService(session).login(payload.username, payload.password)
    return TokenResponse(access_token=token)


@router_auth.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, session: Session = Depends(get_db)) -> TokenResponse:
    token = AuthService(session).register(payload.username, payload.password)
    return TokenResponse(access_token=token)


@router_auth.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user).model_copy(
        update={"is_admin": is_admin(current_user)}
    )
