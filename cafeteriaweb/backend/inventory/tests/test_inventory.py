import os

os.environ["DB_NAME"] = "aroma_inventory_test"

import pytest
from fastapi.testclient import TestClient

import inventory

SECRETOS_PRUEBA = {"gateway": "s-gateway", "graphql": "s-graphql", "orders": "s-orders"}


async def secretos_de_prueba():
    return {"mongodb_uri": "mongodb://localhost:27017", "entrantes": SECRETOS_PRUEBA}


def cabeceras(origen, roles=None, user="USR-1"):
    h = {"X-Service-Name": origen, "X-Service-Secret": SECRETOS_PRUEBA[origen]}
    if roles:
        h["X-Authenticated-User"] = user
        h["X-Authenticated-Roles"] = roles
    return h


@pytest.fixture()
def cliente(monkeypatch):
    monkeypatch.setattr(inventory, "cargar_secretos", secretos_de_prueba)
    with TestClient(inventory.app) as c:
        yield c
        c.portal.call(inventory.client.drop_database, inventory.DB_NAME)


def primer_producto(cliente):
    return cliente.get("/productos", headers=cabeceras("gateway")).json()[0]


def test_acceso_directo_sin_secreto_es_rechazado(cliente):
    assert cliente.get("/productos").status_code == 403


def test_secreto_de_otro_servicio_es_rechazado(cliente):
    h = {"X-Service-Name": "gateway", "X-Service-Secret": SECRETOS_PRUEBA["orders"]}
    assert cliente.get("/productos", headers=h).status_code == 403


def test_catalogo_inicial(cliente):
    r = cliente.get("/productos", headers=cabeceras("gateway"))
    assert r.status_code == 200
    assert len(r.json()) == 8
    assert len(cliente.get("/categorias", headers=cabeceras("gateway")).json()) == 3


def test_cliente_no_puede_modificar_productos(cliente):
    p = primer_producto(cliente)
    r = cliente.patch(f"/productos/{p['id']}/stock", json={"stock": 0, "activo": True},
                      headers=cabeceras("gateway", "cliente"))
    assert r.status_code == 403


def test_admin_actualiza_disponibilidad(cliente):
    p = primer_producto(cliente)
    r = cliente.patch(f"/productos/{p['id']}/stock", json={"stock": 0, "activo": True},
                      headers=cabeceras("gateway", "admin"))
    assert r.status_code == 200
    assert r.json()["disponible"] is False


def test_orders_no_puede_crear_productos(cliente):
    nuevo = {"categoria_id": 3, "nombre": "Brownie", "descripcion": "Chocolate.", "precio": 2000, "stock": 5}
    assert cliente.post("/productos", json=nuevo, headers=cabeceras("orders")).status_code == 403


def test_reserva_descuenta_stock_y_usa_precio_del_servidor(cliente):
    p = primer_producto(cliente)
    r = cliente.post("/reservas", json={"pedido_id": "PED-1", "items": [{"producto_id": p["id"], "cantidad": 2}]},
                     headers=cabeceras("orders"))
    assert r.status_code == 201
    assert r.json()["items"][0]["precio"] == p["precio"]
    stock = cliente.get(f"/productos/{p['id']}", headers=cabeceras("gateway")).json()["stock"]
    assert stock == p["stock"] - 2


def test_reserva_repetida_no_descuenta_dos_veces(cliente):
    p = primer_producto(cliente)
    cuerpo = {"pedido_id": "PED-2", "items": [{"producto_id": p["id"], "cantidad": 3}]}
    cliente.post("/reservas", json=cuerpo, headers=cabeceras("orders"))
    cliente.post("/reservas", json=cuerpo, headers=cabeceras("orders"))
    stock = cliente.get(f"/productos/{p['id']}", headers=cabeceras("gateway")).json()["stock"]
    assert stock == p["stock"] - 3


def test_stock_insuficiente_no_deja_descuentos_parciales(cliente):
    productos = cliente.get("/productos", headers=cabeceras("gateway")).json()
    a, b = productos[0], productos[1]
    cuerpo = {"pedido_id": "PED-3", "items": [{"producto_id": a["id"], "cantidad": 1},
                                              {"producto_id": b["id"], "cantidad": 50}]}
    assert cliente.post("/reservas", json=cuerpo, headers=cabeceras("orders")).status_code == 409
    assert cliente.get(f"/productos/{a['id']}", headers=cabeceras("gateway")).json()["stock"] == a["stock"]


def test_liberar_devuelve_stock_una_sola_vez(cliente):
    p = primer_producto(cliente)
    cliente.post("/reservas", json={"pedido_id": "PED-4", "items": [{"producto_id": p["id"], "cantidad": 4}]},
                 headers=cabeceras("orders"))
    cliente.post("/reservas/PED-4/liberar", headers=cabeceras("orders"))
    cliente.post("/reservas/PED-4/liberar", headers=cabeceras("orders"))
    assert cliente.get(f"/productos/{p['id']}", headers=cabeceras("gateway")).json()["stock"] == p["stock"]


def test_gateway_no_puede_reservar(cliente):
    p = primer_producto(cliente)
    r = cliente.post("/reservas", json={"pedido_id": "PED-5", "items": [{"producto_id": p["id"], "cantidad": 1}]},
                     headers=cabeceras("gateway"))
    assert r.status_code == 403
