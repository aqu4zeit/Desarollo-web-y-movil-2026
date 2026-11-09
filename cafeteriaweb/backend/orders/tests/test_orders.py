import os

os.environ["DB_NAME"] = "aroma_orders_test"

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

import orders

SECRETOS_PRUEBA = {"gateway": "s-gateway", "graphql": "s-graphql", "payments": "s-payments", "despacho": "s-despacho"}
PRODUCTO = "a" * 24
CAMILA = {"id": "x", "user_id": "USR-0005", "nombre": "Camila", "correo": "camila@aroma.cl",
          "direccion": "San Diego 850", "comuna": "Santiago", "telefono": "+56911111111"}


async def secretos_de_prueba():
    return {"mongodb_uri": "mongodb://localhost:27017", "entrantes": SECRETOS_PRUEBA,
            "salientes": {d: "x" for d in orders.DESTINOS}}


class ServiciosFalsos:
    """Reemplaza a inventory, clients, despacho y payments."""

    def __init__(self):
        self.llamadas = []
        self.stock = 10
        self.comuna = "Santiago"
        self.despacho_caido = False

    async def llamar(self, destino, metodo, ruta, json=None, params=None):
        self.llamadas.append((destino, ruta))
        if destino == "clients":
            if ruta.endswith("USR-0005") or ruta.endswith("USR-0006"):
                return httpx.Response(200, json=dict(CAMILA, comuna=self.comuna))
            return httpx.Response(404, json={})
        if destino == "despacho" and ruta == "/cobertura":
            return httpx.Response(200, json={"cubierta": params["comuna"] == "Santiago"})
        if destino == "despacho" and ruta == "/ordenes":
            self.orden = json
            return httpx.Response(503 if self.despacho_caido else 201, json={})
        if destino == "inventory" and ruta == "/reservas":
            cantidad = sum(i["cantidad"] for i in json["items"])
            if cantidad > self.stock:
                return httpx.Response(409, json={"detail": "Stock insuficiente"})
            # inventory responde con SU precio
            return httpx.Response(201, json={"items": [
                {"producto_id": i["producto_id"], "nombre": "Espresso", "precio": 2200, "cantidad": i["cantidad"]}
                for i in json["items"]]})
        return httpx.Response(200, json={})

    def hubo(self, destino, fragmento):
        return any(d == destino and fragmento in r for d, r in self.llamadas)


@pytest.fixture()
def falsos(monkeypatch):
    f = ServiciosFalsos()
    monkeypatch.setattr(orders, "cargar_secretos", secretos_de_prueba)
    monkeypatch.setattr(orders, "llamar", f.llamar)
    return f


@pytest.fixture()
def cliente(falsos):
    with TestClient(orders.app) as c:
        yield c
        c.portal.call(orders.client.drop_database, orders.DB_NAME)


def cabeceras(origen, roles=None, user="USR-0005"):
    h = {"X-Service-Name": origen, "X-Service-Secret": SECRETOS_PRUEBA[origen]}
    if roles:
        h["X-Authenticated-User"] = user
        h["X-Authenticated-Roles"] = roles
    return h


def crear(cliente, cantidad=2, user="USR-0005", **extra):
    return cliente.post("/pedidos", json={"items": [{"producto_id": PRODUCTO, "cantidad": cantidad}]},
                        headers=dict(cabeceras("gateway", "cliente", user), **extra))


def pagar(cliente, pedido_id):
    return cliente.post(f"/interno/pedidos/{pedido_id}/pagado", json={"pago_id": "PAG-1", "folio_boleta": 1},
                        headers=cabeceras("payments"))


def test_el_servidor_calcula_el_total(cliente):
    r = cliente.post("/pedidos", json={"items": [{"producto_id": PRODUCTO, "cantidad": 2, "precio": 1}], "total": 1},
                     headers=cabeceras("gateway", "cliente"))
    assert r.status_code == 201
    assert r.json()["total"] == 4400
    assert r.json()["estado"] == "pendiente_pago"


def test_fuera_de_cobertura(cliente, falsos):
    falsos.comuna = "Maipú"
    assert crear(cliente).status_code == 422


def test_cliente_no_verificado(cliente):
    assert crear(cliente, user="USR-9999").status_code == 403


def test_stock_insuficiente(cliente):
    assert crear(cliente, cantidad=11).status_code == 409


def test_doble_clic_con_la_misma_clave(cliente):
    a = crear(cliente, **{"Idempotency-Key": "k1"}).json()
    b = crear(cliente, **{"Idempotency-Key": "k1"}).json()
    assert a["id"] == b["id"]


def test_pedidos_sin_clave_son_pedidos_distintos(cliente):
    assert crear(cliente).json()["id"] != crear(cliente).json()["id"]


def test_solo_personal_ve_pedidos_ajenos(cliente):
    pid = crear(cliente).json()["id"]
    assert cliente.get(f"/pedidos/{pid}", headers=cabeceras("gateway", "cliente", "USR-0006")).status_code == 404
    assert cliente.get(f"/pedidos/{pid}", headers=cabeceras("gateway", "despacho", "USR-0004")).status_code == 200


def test_dueno_no_ve_datos_personales(cliente):
    pid = crear(cliente).json()["id"]
    r = cliente.get(f"/pedidos/{pid}", headers=cabeceras("gateway", "dueno", "USR-0002"))
    assert r.json()["total"] == 4400 and r.json()["cliente"] == {}
    lista = cliente.get("/pedidos", headers=cabeceras("gateway", "dueno", "USR-0002")).json()
    assert lista[0]["cliente"] == {}
    assert cliente.get(f"/pedidos/{pid}", headers=cabeceras("gateway", "cajero", "USR-0003")).json()["cliente"]


def test_anular_pendiente_devuelve_stock(cliente, falsos):
    pid = crear(cliente).json()["id"]
    r = cliente.post(f"/pedidos/{pid}/anular", json={"motivo": "Cambio de planes"},
                     headers=cabeceras("gateway", "cliente"))
    assert r.json()["estado"] == "anulado"
    assert r.json()["motivo_anulacion"] == "Cambio de planes"
    assert falsos.hubo("inventory", f"/reservas/{pid}/liberar")
    assert not falsos.hubo("payments", "reembolsar")


def test_anular_pagado_pide_reembolso_y_cancela_despacho(cliente, falsos):
    pid = crear(cliente).json()["id"]
    pagar(cliente, pid)
    cliente.post(f"/pedidos/{pid}/anular", json={"motivo": "Me equivoqué"}, headers=cabeceras("gateway", "cliente"))
    assert falsos.hubo("payments", f"/interno/pagos/pedido/{pid}/reembolsar")
    assert falsos.hubo("despacho", f"/ordenes/{pid}/anular")


def test_si_el_reembolso_falla_el_pedido_sigue_pagado(cliente, falsos, monkeypatch):
    pid = crear(cliente).json()["id"]
    pagar(cliente, pid)
    original = falsos.llamar

    async def reembolso_caido(destino, metodo, ruta, json=None, params=None):
        if destino == "payments":
            return httpx.Response(503, json={})
        return await original(destino, metodo, ruta, json, params)

    monkeypatch.setattr(orders, "llamar", reembolso_caido)
    r = cliente.post(f"/pedidos/{pid}/anular", json={"motivo": "Quiero anular"}, headers=cabeceras("gateway", "cliente"))
    assert r.status_code == 502
    assert cliente.get(f"/pedidos/{pid}", headers=cabeceras("gateway", "cliente")).json()["estado"] == "pagado"
    assert not falsos.hubo("inventory", f"/reservas/{pid}/liberar")


def test_otro_cliente_no_anula(cliente):
    pid = crear(cliente).json()["id"]
    r = cliente.post(f"/pedidos/{pid}/anular", json={"motivo": "Intento ajeno"},
                     headers=cabeceras("gateway", "cliente", "USR-0006"))
    assert r.status_code == 404


def test_solo_payments_marca_pagado(cliente):
    pid = crear(cliente).json()["id"]
    r = cliente.post(f"/interno/pedidos/{pid}/pagado", json={"pago_id": "PAG-1", "folio_boleta": 1},
                     headers=cabeceras("gateway", "admin"))
    assert r.status_code == 403


def test_pago_crea_orden_de_despacho_y_reintento_la_recupera(cliente, falsos):
    pid = crear(cliente).json()["id"]
    falsos.despacho_caido = True
    assert pagar(cliente, pid).status_code == 502
    falsos.despacho_caido = False
    r = pagar(cliente, pid)
    assert r.status_code == 200 and r.json()["estado"] == "pagado"


def test_transiciones_invalidas(cliente):
    pid = crear(cliente).json()["id"]
    r = cliente.post(f"/interno/pedidos/{pid}/estado", json={"estado": "en_preparacion"}, headers=cabeceras("despacho"))
    assert r.status_code == 409  # sin pago no se prepara
    pagar(cliente, pid)
    r = cliente.post(f"/interno/pedidos/{pid}/estado", json={"estado": "entregado"}, headers=cabeceras("despacho"))
    assert r.status_code == 409  # no se salta la preparacion


def test_pedido_sin_pagar_vence(cliente, falsos):
    pid = crear(cliente).json()["id"]
    viejo = datetime.now(timezone.utc) - timedelta(minutes=orders.MINUTOS_PARA_PAGAR + 1)
    cliente.portal.call(orders.db.pedidos.update_one, {"_id": pid}, {"$set": {"creado": viejo}})
    cliente.portal.call(orders.vencer_pendientes)
    r = cliente.get(f"/pedidos/{pid}", headers=cabeceras("gateway", "cliente"))
    assert r.json()["estado"] == "anulado"
    assert falsos.hubo("inventory", f"/reservas/{pid}/liberar")
