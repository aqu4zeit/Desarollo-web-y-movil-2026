import os

os.environ["DB_NAME"] = "aroma_clients_test"

import re

import httpx
import pytest
from fastapi.testclient import TestClient

import clients

SECRETOS_PRUEBA = {"gateway": "s-gateway", "graphql": "s-graphql", "orders": "s-orders", "payments": "s-payments"}

REGISTRO = {
    "nombre": "Diego Muñoz", "direccion": "Los Pajaritos 2200", "comuna": "Maipú", "provincia": "Santiago",
    "region": "Metropolitana", "telefono": "+56922222222", "run": "12345678-5", "fecha_nacimiento": "1995-06-01",
    "sexo": "masculino", "correo": "diego@gmail.com", "password": "Diego2026!"
}


async def secretos_de_prueba():
    return {"mongodb_uri": "mongodb://localhost:27017", "entrantes": SECRETOS_PRUEBA,
            "salientes": {"auth": "x", "mensajeria": "y"}}


class ServiciosFalsos:
    """Reemplaza al Auth Service y a la API de mensajeria."""

    def __init__(self):
        self.correos = []
        self.activados = []

    async def llamar(self, destino, url, metodo, ruta, json=None):
        if destino == "mensajeria" and ruta == "/validar":
            return httpx.Response(200, json={"existe": not json["correo"].endswith("@noexiste.cl")})
        if destino == "mensajeria" and ruta == "/enviar":
            self.correos.append(json)
            return httpx.Response(202, json={"estado": "aceptado"})
        if destino == "auth" and ruta == "/usuarios":
            # El registro nunca crea credenciales activas ni con otro rol
            assert json["roles"] == ["cliente"] and json["activo"] is False
            return httpx.Response(201, json={"id": "USR-TEST"})
        if destino == "auth" and ruta.endswith("/activar"):
            self.activados.append(ruta)
            return httpx.Response(200, json={})
        raise AssertionError(f"llamada inesperada {destino} {ruta}")

    def ultimo_codigo(self):
        return re.search(r"\d{6}", self.correos[-1]["cuerpo"]).group()


@pytest.fixture()
def falsos(monkeypatch):
    f = ServiciosFalsos()
    monkeypatch.setattr(clients, "cargar_secretos", secretos_de_prueba)
    monkeypatch.setattr(clients, "llamar", f.llamar)
    return f


@pytest.fixture()
def cliente(falsos):
    with TestClient(clients.app) as c:
        yield c
        c.portal.call(clients.client.drop_database, clients.DB_NAME)


def cabeceras(origen, roles=None, user="USR-TEST"):
    h = {"X-Service-Name": origen, "X-Service-Secret": SECRETOS_PRUEBA[origen]}
    if roles:
        h["X-Authenticated-User"] = user
        h["X-Authenticated-Roles"] = roles
    return h


def registrar(cliente, **cambios):
    return cliente.post("/clientes/registro", json=dict(REGISTRO, **cambios), headers=cabeceras("gateway"))


def test_registro_envia_codigo_y_no_guarda_la_clave(cliente, falsos):
    r = registrar(cliente)
    assert r.status_code == 201
    assert falsos.correos[-1]["para"] == "diego@gmail.com"
    doc = cliente.portal.call(clients.db.clientes.find_one, {"correo": "diego@gmail.com"})
    assert "password" not in doc
    assert doc["verificado"] is False


def test_validaciones_de_registro(cliente):
    assert registrar(cliente, run="12345678-0").status_code == 422
    assert registrar(cliente, telefono="12345").status_code == 422
    assert registrar(cliente, fecha_nacimiento="2999-01-01").status_code == 422
    assert registrar(cliente, correo="diego@noexiste.cl").status_code == 422


def test_registro_duplicado(cliente):
    registrar(cliente)
    assert registrar(cliente).status_code == 409


def test_verificacion_del_correo(cliente, falsos):
    registrar(cliente)
    malo = cliente.post("/clientes/verificar", json={"correo": "diego@gmail.com", "codigo": "000000"},
                        headers=cabeceras("gateway"))
    assert malo.status_code == 400
    ok = cliente.post("/clientes/verificar", json={"correo": "diego@gmail.com", "codigo": falsos.ultimo_codigo()},
                      headers=cabeceras("gateway"))
    assert ok.status_code == 200
    assert falsos.activados == ["/usuarios/USR-TEST/activar"]


def test_codigo_se_bloquea_tras_cinco_intentos(cliente, falsos):
    registrar(cliente)
    for _ in range(5):
        cliente.post("/clientes/verificar", json={"correo": "diego@gmail.com", "codigo": "000000"},
                     headers=cabeceras("gateway"))
    r = cliente.post("/clientes/verificar", json={"correo": "diego@gmail.com", "codigo": falsos.ultimo_codigo()},
                     headers=cabeceras("gateway"))
    assert r.status_code == 400


def test_perfil_propio_por_identidad_del_gateway(cliente):
    r = cliente.get("/clientes/me", headers=cabeceras("gateway", "cliente", "USR-0005"))
    assert r.status_code == 200
    assert r.json()["correo"] == "camila@aroma.cl"


def test_cliente_no_usa_el_mantenedor(cliente):
    assert cliente.get("/clientes", headers=cabeceras("gateway", "cliente", "USR-0005")).status_code == 403
    assert cliente.get("/clientes", headers=cabeceras("gateway", "admin", "USR-0001")).status_code == 200


def test_resumen_interno_solo_para_servicios(cliente):
    assert cliente.get("/interno/clientes/USR-0005", headers=cabeceras("gateway")).status_code == 403
    r = cliente.get("/interno/clientes/USR-0005", headers=cabeceras("orders"))
    assert r.status_code == 200
    # El resumen no incluye RUN ni fecha de nacimiento
    assert "run" not in r.json() and "fecha_nacimiento" not in r.json()


def test_acceso_directo_rechazado(cliente):
    assert cliente.get("/clientes/me").status_code == 403
