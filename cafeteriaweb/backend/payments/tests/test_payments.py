import os

os.environ["DB_NAME"] = "aroma_payments_test"

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

import payments

SECRETOS_PRUEBA = {"gateway": "s-gateway", "orders": "s-orders", "graphql": "s-graphql"}
CLAVE_FIRMA = "clave-de-firma"

PEDIDO = {
    "id": "PED-1", "user_id": "USR-0005", "total": 6900, "estado": "pendiente_pago",
    "cliente": {"nombre": "Camila", "correo": "camila@aroma.cl"},
    "items": [{"nombre": "Espresso", "cantidad": 2, "precio": 2200, "subtotal": 4400},
              {"nombre": "Croissant", "cantidad": 1, "precio": 2500, "subtotal": 2500}],
}


async def secretos_de_prueba():
    return {"mongodb_uri": "mongodb://localhost:27017", "entrantes": SECRETOS_PRUEBA,
            "salientes": {"orders": "x", "mensajeria": "y"},
            "proveedor": {"api_key": "k", "clave_firma": CLAVE_FIRMA}}


class ServiciosFalsos:
    """Reemplaza a orders, mensajeria y la plataforma de pago."""

    def __init__(self):
        self.pedido = dict(PEDIDO)
        self.respuesta_orders = 200
        self.correos = []
        self.pagados = []
        self.reembolsos = []

    async def llamar(self, destino, metodo, ruta, json=None):
        if destino == "orders" and metodo == "GET":
            return httpx.Response(200, json=self.pedido)
        if destino == "orders" and ruta.endswith("/pagado"):
            if self.respuesta_orders == 200:
                self.pagados.append(json)
            return httpx.Response(self.respuesta_orders, json={})
        if destino == "mensajeria":
            self.correos.append(json)
            return httpx.Response(202, json={})
        raise AssertionError(ruta)

    async def llamar_proveedor(self, metodo, ruta, json=None):
        if ruta == "/transacciones":
            return httpx.Response(201, json={"token": "tok-1", "url_pago": "http://localhost:9500/pagar/tok-1"})
        if ruta.endswith("/reembolso"):
            self.reembolsos.append(ruta)
            return httpx.Response(200, json={})
        raise AssertionError(ruta)


@pytest.fixture()
def falsos(monkeypatch):
    f = ServiciosFalsos()
    monkeypatch.setattr(payments, "cargar_secretos", secretos_de_prueba)
    monkeypatch.setattr(payments, "llamar", f.llamar)
    monkeypatch.setattr(payments, "llamar_proveedor", f.llamar_proveedor)
    return f


@pytest.fixture()
def cliente(falsos):
    with TestClient(payments.app) as c:
        yield c
        c.portal.call(payments.client.drop_database, payments.DB_NAME)


def cabeceras(origen, roles=None, user="USR-0005"):
    h = {"X-Service-Name": origen, "X-Service-Secret": SECRETOS_PRUEBA[origen]}
    if roles:
        h["X-Authenticated-User"] = user
        h["X-Authenticated-Roles"] = roles
    return h


def iniciar(cliente, user="USR-0005"):
    return cliente.post("/pagos", json={"pedido_id": "PED-1"}, headers=cabeceras("gateway", "cliente", user))


def aviso(cliente, pago, estado="aprobado", evento_id=None, monto=None, fecha=None, firma=None):
    evento = {"evento_id": evento_id or str(uuid.uuid4()), "token": "tok-1", "referencia": pago["id"],
              "estado": estado, "monto": monto or pago["monto"],
              "fecha": (fecha or datetime.now(timezone.utc)).isoformat()}
    cuerpo = json.dumps(evento).encode()
    firma = firma or hmac.new(CLAVE_FIRMA.encode(), cuerpo, hashlib.sha256).hexdigest()
    return cliente.post("/notificaciones", content=cuerpo,
                        headers=dict(cabeceras("gateway"), **{"X-Firma": firma, "Content-Type": "application/json"}))


def contar(cliente, coleccion):
    return cliente.portal.call(payments.db[coleccion].count_documents, {})


def test_monto_sale_del_pedido(cliente):
    r = iniciar(cliente)
    assert r.status_code == 201
    assert r.json()["monto"] == 6900


def test_pedido_ajeno_o_no_pendiente(cliente, falsos):
    assert iniciar(cliente, user="USR-0006").status_code == 404
    falsos.pedido["estado"] = "pagado"
    assert iniciar(cliente).status_code == 409


def test_reutiliza_el_intento_abierto(cliente):
    assert iniciar(cliente).json()["id"] == iniciar(cliente).json()["id"]


def test_aviso_con_firma_invalida(cliente):
    pago = iniciar(cliente).json()
    assert aviso(cliente, pago, firma="0" * 64).status_code == 401


def test_aviso_vencido_o_con_otro_monto(cliente):
    pago = iniciar(cliente).json()
    assert aviso(cliente, pago, fecha=datetime.now(timezone.utc) - timedelta(hours=1)).status_code == 400
    assert aviso(cliente, pago, monto=1).status_code == 400


def test_pago_aprobado_genera_venta_boleta_y_correo(cliente, falsos):
    pago = iniciar(cliente).json()
    r = aviso(cliente, pago)
    assert r.json()["resultado"] == "aprobado"
    assert falsos.pagados == [{"pago_id": pago["id"], "folio_boleta": 1}]
    boleta = cliente.get("/boletas/pedido/PED-1", headers=cabeceras("gateway", "cliente")).json()
    assert boleta["total"] == 6900 and boleta["neto"] + boleta["iva"] == 6900
    assert boleta["caja"]["id"] == "CAJA-WEB-01"
    assert falsos.correos[-1]["para"] == "camila@aroma.cl"


def test_aviso_duplicado_no_cobra_dos_veces(cliente):
    pago = iniciar(cliente).json()
    aviso(cliente, pago, evento_id="evt-1")
    r = aviso(cliente, pago, evento_id="evt-1")
    assert r.json()["resultado"] == "duplicado"
    aviso(cliente, pago, evento_id="evt-2")
    assert contar(cliente, "ventas") == 1
    assert contar(cliente, "boletas") == 1


def test_orders_caido_se_completa_con_el_reintento(cliente, falsos):
    pago = iniciar(cliente).json()
    falsos.respuesta_orders = 503
    assert aviso(cliente, pago, evento_id="evt-1").status_code == 502
    falsos.respuesta_orders = 200
    aviso(cliente, pago, evento_id="evt-1")
    assert len(falsos.pagados) == 1
    assert contar(cliente, "ventas") == 1


def test_pago_de_pedido_anulado_se_devuelve(cliente, falsos):
    pago = iniciar(cliente).json()
    falsos.respuesta_orders = 409
    aviso(cliente, pago)
    assert falsos.reembolsos == ["/transacciones/tok-1/reembolso"]
    boleta = cliente.get("/boletas/pedido/PED-1", headers=cabeceras("gateway", "cliente")).json()
    assert boleta["anulada"] is True


def test_reembolso_pedido_por_orders(cliente, falsos):
    pago = iniciar(cliente).json()
    aviso(cliente, pago)
    r = cliente.post("/interno/pagos/pedido/PED-1/reembolsar", headers=cabeceras("orders"))
    assert r.json()["estado"] == "reembolsado"
    assert cliente.get(f"/pagos/{pago['id']}", headers=cabeceras("gateway", "cliente")).json()["estado"] == "reembolsado"


def test_boleta_ajena_y_ventas_solo_personal(cliente):
    aviso(cliente, iniciar(cliente).json())
    assert cliente.get("/boletas/pedido/PED-1", headers=cabeceras("gateway", "cliente", "USR-0006")).status_code == 404
    assert cliente.get("/ventas", headers=cabeceras("gateway", "cliente")).status_code == 403
    assert len(cliente.get("/ventas", headers=cabeceras("gateway", "dueno", "USR-0002")).json()) == 1


def test_solo_el_gateway_recibe_avisos(cliente):
    iniciar(cliente)
    r = cliente.post("/notificaciones", content=b"{}", headers=dict(cabeceras("orders"), **{"X-Firma": "x"}))
    assert r.status_code == 403
