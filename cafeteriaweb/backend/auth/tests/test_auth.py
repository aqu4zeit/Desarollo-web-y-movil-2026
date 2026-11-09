import os

os.environ["DB_NAME"] = "aroma_auth_test"

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import auth

SECRETOS_PRUEBA = {"gateway": "s-gateway", "clients": "s-clients"}
CLAVES = {"clave_admin": "Admin2026!", "clave_dueno": "Dueno2026!", "clave_cajero": "Cajero2026!",
          "clave_despacho": "Despacho2026!", "clave_cliente": "Camila2026!"}


async def secretos_de_prueba():
    return {"mongodb_uri": "mongodb://localhost:27017", "entrantes": SECRETOS_PRUEBA, **CLAVES}


def cabeceras(origen, roles=None, user="USR-0001"):
    h = {"X-Service-Name": origen, "X-Service-Secret": SECRETOS_PRUEBA[origen]}
    if roles:
        h["X-Authenticated-User"] = user
        h["X-Authenticated-Roles"] = roles
    return h


@pytest.fixture()
def cliente(monkeypatch):
    monkeypatch.setattr(auth, "cargar_secretos", secretos_de_prueba)
    with TestClient(auth.app) as c:
        yield c
        c.portal.call(auth.client.drop_database, auth.DB_NAME)


def login(cliente, username, password):
    return cliente.post("/login", json={"username": username, "password": password}, headers=cabeceras("gateway"))


def test_login_valido_entrega_token(cliente):
    r = login(cliente, "camila@aroma.cl", "Camila2026!")
    assert r.status_code == 200
    assert r.json()["expires_in"] == 900


def test_login_invalido(cliente):
    assert login(cliente, "camila@aroma.cl", "incorrecta").status_code == 401
    assert login(cliente, "nadie@aroma.cl", "x").status_code == 401


def test_login_sin_secreto_del_gateway(cliente):
    r = cliente.post("/login", json={"username": "camila@aroma.cl", "password": "Camila2026!"})
    assert r.status_code == 403


def test_introspeccion_y_logout(cliente):
    token = login(cliente, "camila@aroma.cl", "Camila2026!").json()["access_token"]
    r = cliente.post("/introspect", json={"token": token}, headers=cabeceras("gateway"))
    assert r.json()["active"] is True
    assert r.json()["roles"] == ["cliente"]
    cliente.post("/logout", json={"token": token}, headers=cabeceras("gateway"))
    r = cliente.post("/introspect", json={"token": token}, headers=cabeceras("gateway"))
    assert r.json() == {"active": False}


def test_token_expirado_no_esta_activo(cliente):
    token = login(cliente, "camila@aroma.cl", "Camila2026!").json()["access_token"]
    cliente.portal.call(auth.db.sesiones.update_one, {"_id": auth.hash_token(token)},
                        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)}})
    r = cliente.post("/introspect", json={"token": token}, headers=cabeceras("gateway"))
    assert r.json() == {"active": False}


def test_clave_y_token_no_se_guardan_en_texto_plano(cliente):
    token = login(cliente, "camila@aroma.cl", "Camila2026!").json()["access_token"]
    usuario = cliente.portal.call(auth.db.usuarios.find_one, {"username": "camila@aroma.cl"})
    assert usuario["password_hash"].startswith("$argon2id$")
    assert cliente.portal.call(auth.db.sesiones.find_one, {"_id": token}) is None


def test_clients_solo_crea_clientes_inactivos(cliente):
    datos = {"username": "nuevo@gmail.com", "password": "Clave2026!", "roles": ["admin"], "activo": True}
    assert cliente.post("/usuarios", json=datos, headers=cabeceras("clients")).status_code == 403
    datos = {"username": "nuevo@gmail.com", "password": "Clave2026!", "roles": ["cliente"], "activo": False}
    r = cliente.post("/usuarios", json=datos, headers=cabeceras("clients"))
    assert r.status_code == 201
    # Hasta verificar el correo la cuenta no ingresa
    assert login(cliente, "nuevo@gmail.com", "Clave2026!").status_code == 403
    cliente.post(f"/usuarios/{r.json()['id']}/activar", headers=cabeceras("clients"))
    assert login(cliente, "nuevo@gmail.com", "Clave2026!").status_code == 200


def test_solo_admin_administra_usuarios(cliente):
    assert cliente.get("/usuarios", headers=cabeceras("gateway", "cliente", "USR-0005")).status_code == 403
    assert cliente.get("/usuarios", headers=cabeceras("gateway", "admin")).status_code == 200


def test_cambio_de_perfil_cierra_sesiones(cliente):
    token = login(cliente, "cajero@aroma.cl", "Cajero2026!").json()["access_token"]
    r = cliente.put("/usuarios/USR-0003", json={"roles": ["cajero"], "activo": False},
                    headers=cabeceras("gateway", "admin"))
    assert r.status_code == 200
    assert cliente.post("/introspect", json={"token": token}, headers=cabeceras("gateway")).json()["active"] is False


def test_admin_no_se_quita_su_acceso(cliente):
    r = cliente.put("/usuarios/USR-0001", json={"roles": ["cliente"], "activo": True},
                    headers=cabeceras("gateway", "admin"))
    assert r.status_code == 409
