from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.user import SignupOptionsOut, Token, UserCreate, UserOut
from app.security import DEVICE_COOKIE, DEVICE_TTL, create_device_token, device_account
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/signup-options", response_model=SignupOptionsOut)
def signup_options():
    # Public: the sign-up form renders roles, email domains and password rules from here.
    return SignupOptionsOut()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    return auth_service.register(db, data)


@router.post("/login", response_model=Token)
def login(
    request: Request, response: Response, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    # OAuth2 form uses "username"; we treat it as the 8-digit ID number.
    ip = request.client.host if request.client else "unknown"
    device = device_account(request.cookies.get(DEVICE_COOKIE))
    token = auth_service.login(db, form.username, form.password, ip, device)
    # Renewed on every login. HttpOnly and only sent to this route: page scripts never see it.
    response.set_cookie(
        DEVICE_COOKIE, create_device_token(form.username), max_age=int(DEVICE_TTL.total_seconds()),
        path="/api/auth/login", httponly=True, samesite="strict",
    )
    return Token(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Ends every session of this person, not just this browser: a copied token stops working too.
    auth_service.logout_everywhere(db, user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
