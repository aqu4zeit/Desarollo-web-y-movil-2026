import os

os.environ["DB_NAME"] = "aroma_despacho_test"

import httpx
import pytest
from fastapi.testclient import TestClient

import despacho

SECRETOS_PRUEBA = {"gateway": "s-gateway", "graphql": "s-graphql", "orders": "s-orders"}
ORDEN = {
    "pedido_id": "PED-1",
    "cliente": {"nombre": "Camila <b>Rojas</b>", "correo": "camila@aroma.cl", "direccion": "San Diego 850",
                "comuna": "Santiago", "telefono": "+56911111111"},
    "items": [{"nombre": "Espresso", "cantidad": 2}],
}


async def secretos_de_prueba():
    return {"mongodb_uri": "mongodb://localhost:27017", "entrantes": SECRETOS_PRUEBA, "orders": "x"}


class OrdersFalso:
    def __init__(self):
        self.avisos = []
        self.rechazar = False

    async def avisar(self, pedido_id, estado):
        self.avisos.append(estado)
        return httpx.Response(409 if self.rechazar else 200, json={})


@pytest.fixture()
def orders(monkeypatch):
    f = OrdersFalso()
    monkeypatch.setattr(despacho, "cargar_secretos", secretos_de_prueba)
    monkeypatch.setattr(despacho, "avisar_orders", f.avisar)
    return f


@pytest.fixture()
def cliente(orders):
    with TestClient(despacho.app) as c:
        yield c
        c.portal.call(despacho.client.drop_database, despacho.DB_NAME)


def cabeceras(origen, roles=None, user="USR-0004"):
    h = {"X-Service-Name": origen, "X-Service-Secret": SECRETOS_PRUEBA[origen]}
    if roles:
        h["X-Authenticated-User"] = user
        h["X-Authenticated-Roles"] = roles
    return h


def crear(cliente, pedido_id="PED-1"):
    return cliente.post("/ordenes", json=dict(ORDEN, pedido_id=pedido_id), headers=cabeceras("orders"))


def estado(cliente, cuerpo, roles="despacho"):
    return cliente.patch("/ordenes/PED-1/estado", json=cuerpo, headers=cabeceras("gateway", roles))


def test_cobertura_por_comuna(cliente):
    def cubierta(comuna):
        return cliente.get("/cobertura", params={"comuna": comuna}, headers=cabeceras("orders")).json()["cubierta"]
    assert cubierta("Santiago") and cubierta("ÑUÑOA") and cubierta("Estación  Central")
    assert not cubierta("Maipú") and not cubierta("Puente Alto")


def test_crear_es_idempotente_y_numera_en_orden_de_llegada(cliente):
    assert crear(cliente).json()["numero"] == 1
    assert crear(cliente).json()["numero"] == 1
    assert crear(cliente, "PED-2").json()["numero"] == 2
    cola = cliente.get("/ordenes", headers=cabeceras("gateway", "despacho")).json()
    assert [o["pedido_id"] for o in cola] == ["PED-1", "PED-2"]


def test_flujo_del_encargado(cliente, orders):
    crear(cliente)
    assert estado(cliente, {"estado": "entregada"}).status_code == 409
    assert estado(cliente, {"estado": "en_preparacion"}).status_code == 200
    assert estado(cliente, {"estado": "en_ruta"}).status_code == 422  # falta chofer
    assert estado(cliente, {"estado": "en_ruta", "chofer": "Chofer 1"}).status_code == 200
    assert estado(cliente, {"estado": "entregada"}).json()["estado"] == "entregada"
    assert orders.avisos == ["en_preparacion", "en_despacho", "entregado"]


def test_si_orders_rechaza_no_se_aplica(cliente, orders):
    crear(cliente)
    orders.rechazar = True
    assert estado(cliente, {"estado": "en_preparacion"}).status_code == 409
    assert cliente.get("/ordenes/PED-1", headers=cabeceras("gateway", "despacho")).json()["estado"] == "pendiente"


def test_permisos(cliente):
    crear(cliente)
    assert cliente.get("/ordenes", headers=cabeceras("gateway", "cliente")).status_code == 403
    assert estado(cliente, {"estado": "en_preparacion"}, roles="admin").status_code == 403
    assert cliente.post("/ordenes", json=ORDEN, headers=cabeceras("gateway", "admin")).status_code == 403


def test_anular_solo_antes_de_preparar(cliente):
    crear(cliente)
    estado(cliente, {"estado": "en_preparacion"})
    assert cliente.post("/ordenes/PED-1/anular", headers=cabeceras("orders")).status_code == 409


def test_imprimir_escapa_html(cliente):
    crear(cliente)
    r = cliente.get("/ordenes/PED-1/imprimir", headers=cabeceras("gateway", "despacho"))
    assert "Orden de despacho N° 1" in r.text
    assert "<b>Rojas</b>" not in r.text
