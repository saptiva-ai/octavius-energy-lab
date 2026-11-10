"""El enlace de reseteo de contraseña sirve una sola vez (2026-10-20).

Con el token sin estado, el mismo enlace volvía a cambiar la contraseña
durante sus 30 minutos (verificación en local: la segunda vez daba 200).
Ahora lleva una huella del hash vigente; al cambiar la contraseña, ese enlace
y cualquier otro pendiente dejan de valer.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from src.routers.auth import router as auth_router

pytestmark = [pytest.mark.unit]


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(auth_router)
    return TestClient(app)


class TestResetPasswordUnSoloUso:
    """El enlace de reseteo sirve una sola vez (2026-10-20): con el token sin
    estado, el mismo enlace volvía a cambiar la contraseña durante sus 30
    minutos. Ahora lleva una huella del hash vigente; al cambiar la
    contraseña, ese enlace y cualquier otro pendiente dejan de valer."""

    @staticmethod
    def _settings():
        ajustes = Mock()
        ajustes.secret_key = "test-secret-key-12345"
        ajustes.jwt_algorithm = "HS256"
        return ajustes

    @staticmethod
    def _usuario(password_hash: str):
        usuario = Mock()
        usuario.email = "gerente@example.com"
        usuario.id = "user-123"
        usuario.password_hash = password_hash
        usuario.save = AsyncMock()
        return usuario

    def test_el_mismo_enlace_no_cambia_la_contrasena_dos_veces(self, client):
        from src.core.security import create_password_reset_token

        usuario = self._usuario("hash-original")
        with patch("src.core.security.get_settings", return_value=self._settings()), \
             patch("src.models.user.User") as modelo:
            modelo.find_one = AsyncMock(return_value=usuario)
            token = create_password_reset_token(usuario.email, usuario.password_hash)

            primera = client.post(
                "/auth/reset-password",
                json={"token": token, "new_password": "NuevaClave-12345"},
            )
            assert primera.status_code == status.HTTP_200_OK
            assert usuario.password_hash != "hash-original"
            hash_nuevo = usuario.password_hash

            segunda = client.post(
                "/auth/reset-password",
                json={"token": token, "new_password": "OtraClave-12345"},
            )
            assert segunda.status_code == status.HTTP_400_BAD_REQUEST
            assert "ya se usó" in segunda.json()["detail"]
            assert usuario.password_hash == hash_nuevo
            assert usuario.save.await_count == 1

    def test_un_enlace_pedido_antes_de_cambiar_la_contrasena_ya_no_vale(self, client):
        from src.core.security import create_password_reset_token

        usuario = self._usuario("hash-de-hoy")
        with patch("src.core.security.get_settings", return_value=self._settings()), \
             patch("src.models.user.User") as modelo:
            modelo.find_one = AsyncMock(return_value=usuario)
            viejo = create_password_reset_token(usuario.email, "hash-de-ayer")
            respuesta = client.post(
                "/auth/reset-password",
                json={"token": viejo, "new_password": "NuevaClave-12345"},
            )
            assert respuesta.status_code == status.HTTP_400_BAD_REQUEST
            usuario.save.assert_not_awaited()

    def test_forgot_password_firma_el_enlace_con_el_hash_vigente(self, client):
        usuario = self._usuario("hash-vigente")
        ajustes = self._settings()
        ajustes.smtp_user = "remitente"
        ajustes.smtp_password = "definida"
        ajustes.password_reset_url_base = "https://industryadvisor.example"
        from src.core.config import get_settings

        client.app.dependency_overrides[get_settings] = lambda: ajustes
        try:
            with patch("src.models.user.User") as modelo, \
                 patch("src.routers.auth.create_password_reset_token", return_value="tok") as crear, \
                 patch("src.services.email_service.get_email_service") as correo:
                modelo.find_one = AsyncMock(return_value=usuario)
                correo.return_value.send_password_reset_email = AsyncMock()
                respuesta = client.post(
                    "/auth/forgot-password", json={"email": usuario.email}
                )
            assert respuesta.status_code == status.HTTP_200_OK
            crear.assert_called_once_with(usuario.email, "hash-vigente")
        finally:
            client.app.dependency_overrides.clear()
