import os

os.environ["VAULT_TOKEN"] = "prueba"

import httpx
import pytest
from fastapi.testclient import TestClient

import gateway

IDENTIDADES = {
    "tok-cliente": {"active": True, "user_id": "USR-0005", "username": "camila@aroma.cl",
                    "roles": ["cliente"], "expires_at": "2026-10-21T20:00:00+00:00"},
    "tok-admin": {"active": True, "user_id": "USR-0001", "username": "admin@aroma.cl",
                  "roles": ["admin"], "expires_at": "2026-10-21T20:00:00+00:00"},
}


class ServiciosFalsos:
    """Reemplaza a los servicios internos y registra lo que el gateway les envia."""

    def __init__(self):
        self.llamadas = []
        self.revocados = []

    async def llamar_servicio(self, servicio, metodo, ruta, request, json=None, content=None,
                              params=None, usuario=None):
        self.llamadas.append({"servicio": servicio, "metodo": metodo, "ruta": ruta, "usuario": usuario})
        if servicio == "auth" and ruta == "/introspect":
            return httpx.Response(200, json=IDENTIDADES.get(json["token"], {"active": False}))
        if servicio == "auth" and ruta == "/login":
            if json["password"] != "correcta":
                return httpx.Response(401, json={"detail": "Credenciales incorrectas"})
            return httpx.Response(200, json={"access_token": "tok-cliente", "expires_in": 900})
        if servicio == "auth" and ruta == "/logout":
            self.revocados.append(json["token"])
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"ok": True})

    def ultima(self):
        return self.llamadas[-1]


@pytest.fixture()
def falsos(monkeypatch):
    f = ServiciosFalsos()
    monkeypatch.setattr(gateway, "llamar_servicio", f.llamar_servicio)
    gateway.VENTANAS.clear()
    return f


@pytest.fixture()
def cliente(falsos):
    return TestClient(gateway.app)


def test_ruta_publica_sin_sesion(cliente, falsos):
    assert cliente.get("/api/productos").status_code == 200
    assert falsos.ultima() == {"servicio": "inventory", "metodo": "GET", "ruta": "/productos", "usuario": None}


def test_ruta_no_listada_y_metodo_no_permitido(cliente):
    assert cliente.get("/api/reservas").status_code == 404
    assert cliente.patch("/api/productos/abc").status_code == 405


def test_ruta_protegida_sin_sesion(cliente):
    assert cliente.get("/api/clientes/me").status_code == 401


def test_token_invalido(cliente):
    assert cliente.get("/api/clientes/me", headers={"Authorization": "Bearer inventado"}).status_code == 401


def test_rol_insuficiente(cliente):
    r = cliente.get("/api/usuarios", headers={"Authorization": "Bearer tok-cliente"})
    assert r.status_code == 403


def test_admin_autorizado(cliente, falsos):
    r = cliente.get("/api/usuarios", headers={"Authorization": "Bearer tok-admin"})
    assert r.status_code == 200
    assert falsos.ultima()["servicio"] == "auth"


def test_identidad_viene_de_la_introspeccion_no_del_navegador(cliente, falsos):
    cliente.get("/api/clientes/me", headers={
        "Authorization": "Bearer tok-cliente",
        "X-Authenticated-User": "USR-0001",
        "X-Authenticated-Roles": "admin",
    })
    assert falsos.ultima()["usuario"]["user_id"] == "USR-0005"
    assert falsos.ultima()["usuario"]["roles"] == ["cliente"]


def test_cabeceras_falsas_sin_token_no_dan_acceso(cliente):
    r = cliente.get("/api/usuarios", headers={"X-Authenticated-User": "USR-0001", "X-Authenticated-Roles": "admin"})
    assert r.status_code == 401


def test_parametros_de_ruta_seguros(cliente):
    assert cliente.get("/api/productos/..%2Fusuarios").status_code == 404


def test_login_crea_cookie_httponly(cliente):
    r = cliente.post("/auth/login", json={"username": "camila@aroma.cl", "password": "correcta"})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert "session_token=tok-cliente" in cookie
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    # El token no se entrega al JavaScript del navegador
    assert "tok-cliente" not in r.text


def test_login_incorrecto(cliente):
    r = cliente.post("/auth/login", json={"username": "camila@aroma.cl", "password": "mala"})
    assert r.status_code == 401
    assert "set-cookie" not in r.headers


def test_me_y_logout_con_cookie(cliente, falsos):
    cliente.cookies.set("session_token", "tok-cliente")
    assert cliente.get("/auth/me").json()["username"] == "camila@aroma.cl"
    r = cliente.post("/auth/logout")
    assert r.status_code == 200
    assert falsos.revocados == ["tok-cliente"]
    assert 'session_token=""' in r.headers["set-cookie"]


def test_limite_de_intentos_de_login(cliente):
    codigos = [cliente.post("/auth/login", json={"username": "a@a.cl", "password": "mala"}).status_code
               for _ in range(11)]
    assert codigos[:10] == [401] * 10
    assert codigos[10] == 429


def test_correlation_id_y_cabeceras_de_seguridad(cliente):
    r = cliente.get("/health")
    assert len(r.headers["x-correlation-id"]) == 36
    assert r.headers["x-frame-options"] == "DENY"


def test_servicio_caido(monkeypatch):
    # Sin reemplazo: el gateway intenta conectar a un servicio que no existe
    monkeypatch.setattr(gateway, "get_gateway_secrets", lambda: _secretos())
    monkeypatch.setitem(gateway.SERVICIOS, "inventory", "http://127.0.0.1:1")
    gateway.VENTANAS.clear()
    r = TestClient(gateway.app).get("/api/productos")
    assert r.status_code == 502


async def _secretos():
    return {"auth": "a", "inventory": "i", "clients": "c"}
