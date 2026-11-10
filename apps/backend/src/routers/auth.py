"""
Authentication routes for the Copilot OS API.
"""

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.security import OAuth2PasswordBearer

from ..core.config import Settings, get_settings
from ..core.exceptions import APIError, AuthenticationError

# Import stateless security utils
from ..core.security import (
    create_password_reset_token,
    verificar_huella_reset,
    verify_password_reset_token,
)
from ..schemas.auth import (
    AuthRequest,
    AuthResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    RefreshResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenRefresh,
)
from ..schemas.user import User as UserSchema
from ..schemas.user import UserCreate
from ..services.auth_service import (
    authenticate_user,
    get_user_profile,
    logout_user,
    refresh_access_token,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def _set_session_cookie(
    response: Response, token: str, max_age: int, settings: Settings
) -> None:
    samesite = (settings.session_cookie_samesite or "lax").lower()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        domain=settings.session_cookie_domain,
        path=settings.session_cookie_path,
        samesite=samesite,
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        domain=settings.session_cookie_domain,
        path=settings.session_cookie_path,
    )


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def register(payload: UserCreate) -> AuthResponse:
    """Register a new user."""
    return await register_user(payload)


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: AuthRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    """Authenticate a user and issue tokens."""
    auth_response = await authenticate_user(payload.identifier, payload.password)
    _set_session_cookie(
        response, auth_response.access_token, auth_response.expires_in, settings
    )
    return auth_response


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    payload: TokenRefresh,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> RefreshResponse:
    """Refresh an access token using a refresh token."""
    refreshed = await refresh_access_token(payload.refresh_token)
    _set_session_cookie(
        response, refreshed.access_token, refreshed.expires_in, settings
    )
    return refreshed


@router.get("/me", response_model=UserSchema)
async def me(request: Request) -> UserSchema:
    """Retrieve the current authenticated user profile."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise AuthenticationError("Not authenticated")

    return await get_user_profile(str(user_id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: TokenRefresh,
    response: Response,
    token: str = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings),
) -> None:
    """Logout user and invalidate session.

    P0-LOGOUT-INVALIDATE: Blacklist the refresh token to prevent reuse.
    The access token from the Authorization header is also blacklisted for completeness.
    """
    # Blacklist the refresh token (most important - has longer expiry)
    if payload.refresh_token:
        await logout_user(payload.refresh_token)

    # Also blacklist the access token if provided
    if token:
        await logout_user(token)

    _clear_session_cookie(response, settings)

    return None


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_200_OK,
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
) -> ForgotPasswordResponse:
    """
    Request password reset email.

    Sends a password reset link to the user's email address.
    The link is valid for 30 minutes (stateless JWT).
    """
    import structlog

    from ..models.user import User
    from ..services.email_service import get_email_service

    logger = structlog.get_logger(__name__)

    try:
        # Validate SMTP configuration early
        if not settings.smtp_user or not settings.smtp_password:
            logger.error(
                "SMTP configuration missing - password reset unavailable",
                smtp_user_set=bool(settings.smtp_user),
                smtp_password_set=bool(settings.smtp_password),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El servicio de recuperación de contraseña no está configurado. Por favor contacte al administrador.",
            )

        # Find user by email
        user = await User.find_one(User.email == payload.email)

        # Always return success to prevent email enumeration
        if not user:
            logger.warning(
                "Password reset requested for non-existent email", email=payload.email
            )
            return ForgotPasswordResponse(
                message="Si el correo existe en nuestro sistema, recibirás un enlace de recuperación",
                email=payload.email,
            )

        # Create stateless reset token (JWT), tied to the current password hash
        # so the link works only once.
        token = create_password_reset_token(user.email, user.password_hash)

        # Generate reset link
        reset_link = f"{settings.password_reset_url_base}/reset-password?token={token}"

        # Send email using background task
        email_service = get_email_service()

        # Using background_tasks for non-blocking email sending
        background_tasks.add_task(
            email_service.send_password_reset_email,
            to_email=user.email,
            username=user.username,
            reset_link=reset_link,
        )

        logger.info(
            "Password reset email task scheduled",
            email=user.email,
            user_id=str(user.id),
            reset_url_base=settings.password_reset_url_base,
        )

        return ForgotPasswordResponse(
            message="Si el correo existe en nuestro sistema, recibirás un enlace de recuperación",
            email=payload.email,
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(
            "Unexpected error in forgot-password endpoint",
            error=str(e),
            error_type=type(e).__name__,
            email=payload.email,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar la solicitud de recuperación de contraseña. Por favor intente nuevamente.",
        )


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    status_code=status.HTTP_200_OK,
)
async def reset_password(
    payload: ResetPasswordRequest,
) -> ResetPasswordResponse:
    """
    Reset password using token from email.

    The token must be valid and not expired (30 minutes limit).
    """
    import structlog

    from ..models.user import User

    logger = structlog.get_logger(__name__)

    # Validate token (stateless)
    email = verify_password_reset_token(payload.token)

    # Find user by email
    user = await User.find_one(User.email == email)
    if not user:
        logger.error("Password reset token valid but user not found", email=email)
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario no encontrado"
        )

    # One use: the token carries a fingerprint of the hash it was issued for.
    verificar_huella_reset(payload.token, user.password_hash)

    # Update password
    from passlib.hash import argon2

    user.password_hash = argon2.hash(payload.new_password)
    await user.save()

    logger.info("Password successfully reset", user_id=str(user.id), email=user.email)

    return ResetPasswordResponse(
        message="Contraseña actualizada exitosamente. Ahora puedes iniciar sesión con tu nueva contraseña."
    )
