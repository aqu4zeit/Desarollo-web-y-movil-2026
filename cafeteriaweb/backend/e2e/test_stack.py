# Pruebas de integracion del sistema completo (Docker levantado con preparar.ps1).
# Ejecutar desde backend/:  python -m pytest e2e/test_stack.py -q
import json
import random
import time

import httpx
import pytest

from conftest import (BASE, compose, correos, en_red_privada, esperar_estado, ingresar, leer_env, pagar_en_pasarela,
                      run_valido)

# Datos que comparten las pruebas (se ejecutan en orden)
ESTADO = {}


def crear_pedido(cliente, producto, cantidad):
    r = cliente.post("/api/pedidos", json={"items": [{"producto_id": producto["id"], "cantidad": cantidad}]})
    assert r.status_code == 201, r.text
    return r.json()


def pagar(cliente, pedido_id, accion="aprobar"):
    r = cliente.post("/api/pagos", json={"pedido_id": pedido_id})
    assert r.status_code == 201, r.text
    assert pagar_en_pasarela(r.json()["url_pago"], accion).status_code == 303
    return r.json()


def stock(producto_id):
    return httpx.get(f"{BASE}/api/productos/{producto_id}").json()["stock"]


# A. Frontera: los servicios internos no se ven desde fuera de Docker
@pytest.mark.parametrize("puerto", [8100, 8090, 8200, 9000, 9100, 9200, 9300, 9400, 9600, 27017])
def test_servicios_internos_sin_puerto_publico(puerto):
    with pytest.raises(httpx.TransportError):
        httpx.get(f"http://localhost:{puerto}/", timeout=2.0)


# A. Dentro de la red privada, sin la credencial del tramo, todos rechazan (403)
def test_servicios_rechazan_llamadas_sin_credencial():
    codigo = """
import httpx, json
destinos = [("GET", "http://inventory:9100/productos"), ("GET", "http://clients:9000/clientes/me"),
            ("GET", "http://orders:9200/pedidos/mios"), ("GET", "http://payments:9300/ventas"),
            ("GET", "http://despacho:9400/ordenes"), ("GET", "http://auth:8100/usuarios"),
            ("POST", "http://graphql:8090/graphql")]
cabeceras = {"X-Service-Name": "gateway", "X-Service-Secret": "adivinado",
             "X-Authenticated-User": "USR-0001", "X-Authenticated-Roles": "admin"}
print(json.dumps([httpx.request(m, u, headers=cabeceras, json={}).status_code for m, u in destinos]))
"""
    assert json.loads(en_red_privada(codigo)) == [403] * 7


# B. Login incorrecto
def test_login_incorrecto():
    r = httpx.post(f"{BASE}/auth/login", json={"username": "camila@aroma.cl", "password": "incorrecta"})
    assert r.status_code == 401
    assert "set-cookie" not in r.headers


# C. Login con cookie HttpOnly y sesion activa
def test_login_crea_cookie_httponly_y_sesion(camila):
    cookie = [c for c in camila.cookies.jar if c.name == "session_token"][0]
    assert cookie.has_nonstandard_attr("HttpOnly")
    me = camila.get("/auth/me").json()
    assert me["username"] == "camila@aroma.cl" and me["roles"] == ["cliente"]


# D. Autorizacion por rol y cabeceras de identidad falsificadas
def test_roles(camila, admin):
    assert camila.get("/api/usuarios").status_code == 403
    assert admin.get("/api/usuarios").status_code == 200
    falsa = httpx.get(f"{BASE}/api/usuarios", headers={"X-Authenticated-User": "USR-0001", "X-Authenticated-Roles": "admin"})
    assert falsa.status_code == 401


# Compra completa: el servidor calcula el precio, el pago confirma, sale la boleta
def test_compra_completa(camila, productos):
    espresso = productos["Espresso"]
    stock_antes = stock(espresso["id"])
    r = camila.post("/api/pedidos", json={"items": [{"producto_id": espresso["id"], "cantidad": 2, "precio": 1}],
                                          "total": 1})
    pedido = r.json()
    assert pedido["total"] == 2 * espresso["precio"]
    assert stock(espresso["id"]) == stock_antes - 2

    pago = pagar(camila, pedido["id"])
    pedido = esperar_estado(camila, pedido["id"], "pagado")
    boleta = camila.get(f"/api/boletas/pedido/{pedido['id']}").json()
    assert boleta["total"] == pedido["total"] and boleta["neto"] + boleta["iva"] == boleta["total"]
    assert any(f"N° {boleta['folio']}" in m["asunto"] for m in correos("camila@aroma.cl"))
    ESTADO.update(pedido=pedido["id"], pago=pago["id"], folio=boleta["folio"])


# Pago duplicado: el proveedor repite el aviso y no se registra otra venta
def test_aviso_de_pago_duplicado(admin):
    env = leer_env()
    token = compose("exec", "-T", "mongo", "mongosh", "--quiet", "-u", "root", "-p", env["MONGO_ROOT_PASSWORD"],
                    "--authenticationDatabase", "admin", "--eval",
                    f"print(db.getSiblingDB('aroma_payments').pagos.findOne({{_id: '{ESTADO['pago']}'}}).token)")
    r = httpx.post(f"http://localhost:9500/transacciones/{token}/reenviar-aviso",
                   headers={"X-Api-Key": env["PROVEEDOR_API_KEY"]})
    assert r.json()["respuesta_comercio"] == 200
    ventas = [v for v in admin.get("/api/ventas?limit=500").json() if v["pedido_id"] == ESTADO["pedido"]]
    assert len(ventas) == 1


def test_aviso_falsificado():
    evento = {"evento_id": "falso", "token": "x", "referencia": ESTADO["pago"], "estado": "aprobado",
              "monto": 1, "fecha": "2026-01-01T00:00:00+00:00"}
    r = httpx.post(f"{BASE}/api/pagos/notificacion", json=evento, headers={"X-Firma": "0" * 64})
    assert r.status_code == 401


# Propiedad del recurso: otro cliente no ve ni anula el pedido de Camila
def test_otro_cliente_no_accede_a_pedidos_ajenos(cliente_nuevo):
    assert cliente_nuevo.get(f"/api/pedidos/{ESTADO['pedido']}").status_code == 404
    assert cliente_nuevo.get(f"/api/boletas/pedido/{ESTADO['pedido']}").status_code == 404
    r = cliente_nuevo.post(f"/api/pedidos/{ESTADO['pedido']}/anular", json={"motivo": "Intento ajeno"})
    assert r.status_code == 404
    consulta = {"query": f'{{ pedido(id: "{ESTADO["pedido"]}") {{ id total }} }}'}
    assert cliente_nuevo.post("/api/graphql", json=consulta).json()["data"]["pedido"] is None


# Despacho: el encargado avanza el pedido hasta entregarlo
def test_flujo_de_despacho(encargado, camila):
    ruta = f"/api/despacho/ordenes/{ESTADO['pedido']}/estado"
    assert camila.patch(ruta, json={"estado": "en_preparacion"}).status_code == 403
    assert encargado.patch(ruta, json={"estado": "entregada"}).status_code == 409
    assert encargado.patch(ruta, json={"estado": "en_preparacion"}).status_code == 200
    assert encargado.patch(ruta, json={"estado": "en_ruta", "chofer": "Chofer 1"}).status_code == 200
    assert encargado.patch(ruta, json={"estado": "entregada"}).status_code == 200
    assert camila.get(f"/api/pedidos/{ESTADO['pedido']}").json()["estado"] == "entregado"
    anular = camila.post(f"/api/pedidos/{ESTADO['pedido']}/anular", json={"motivo": "Ya lo recibí"})
    assert anular.status_code == 409


# Anular un pedido pagado: motivo obligatorio, devuelve stock y dinero
def test_anular_pagado_recupera_stock_y_reembolsa(camila, productos):
    cheesecake = productos["Cheesecake"]
    antes = stock(cheesecake["id"])
    pedido = crear_pedido(camila, cheesecake, 2)
    pago = pagar(camila, pedido["id"])
    esperar_estado(camila, pedido["id"], "pagado")
    assert camila.post(f"/api/pedidos/{pedido['id']}/anular", json={"motivo": ""}).status_code == 422
    r = camila.post(f"/api/pedidos/{pedido['id']}/anular", json={"motivo": "Me equivoqué de producto"})
    assert r.json()["estado"] == "anulado"
    assert stock(cheesecake["id"]) == antes
    assert camila.get(f"/api/pagos/{pago['id']}").json()["estado"] == "reembolsado"
    assert camila.get(f"/api/boletas/pedido/{pedido['id']}").json()["anulada"] is True


def test_pago_rechazado_deja_el_pedido_pendiente(camila, productos):
    pedido = crear_pedido(camila, productos["Croissant"], 1)
    pago = pagar(camila, pedido["id"], "rechazar")
    time.sleep(1)
    assert camila.get(f"/api/pagos/{pago['id']}").json()["estado"] == "rechazado"
    assert camila.get(f"/api/pedidos/{pedido['id']}").json()["estado"] == "pendiente_pago"
    camila.post(f"/api/pedidos/{pedido['id']}/anular", json={"motivo": "Prueba de pago rechazado"})


def test_stock_insuficiente_y_cobertura(cliente_nuevo, productos):
    latte = productos["Latte helado"]["id"]
    assert cliente_nuevo.post("/api/pedidos", json={"items": [{"producto_id": latte, "cantidad": 50}]}).status_code == 409
    perfil = cliente_nuevo.get("/api/clientes/me").json()
    datos = {k: perfil[k] for k in ("nombre", "direccion", "comuna", "provincia", "region", "telefono")}
    cliente_nuevo.put("/api/clientes/me", json=dict(datos, comuna="Puente Alto"))
    r = cliente_nuevo.post("/api/pedidos", json={"items": [{"producto_id": latte, "cantidad": 1}]})
    cliente_nuevo.put("/api/clientes/me", json=datos)
    assert r.status_code == 422 and "No hay despacho" in r.json()["detail"]


# GraphQL: agregacion, autorizacion por operacion y por campo, y limite de costo
def test_graphql(camila, dueno):
    anio = '(desde: "2026-01-01", hasta: "2026-12-31")'
    resumen = dueno.post("/api/graphql", json={"query": "{ resumenVentas" + anio +
                                                         " { cantidadVentas totalVendido pedidosPorEstado { estado cantidad } } }"}).json()
    assert resumen["data"]["resumenVentas"]["cantidadVentas"] >= 1
    prohibido = camila.post("/api/graphql", json={"query": "{ resumenVentas" + anio + " { totalVendido } }"}).json()
    assert prohibido["errors"][0]["extensions"]["code"] == "FORBIDDEN"
    campo = dueno.post("/api/graphql", json={"query": f'{{ pedido(id: "{ESTADO["pedido"]}") {{ total cliente {{ telefono }} }} }}'}).json()
    assert campo["data"]["pedido"]["total"] > 0 and campo["data"]["pedido"]["cliente"] is None
    alias = " ".join(f"a{i}: misPedidos {{ id estado total }}" for i in range(40))
    assert camila.post("/api/graphql", json={"query": "{ " + alias + " }"}).status_code == 400


# Dependencia caida: si payments no responde, mis pedidos llegan igual con error parcial
def test_dependencia_caida_error_parcial(camila):
    compose("stop", "payments")
    try:
        r = camila.post("/api/graphql", json={"query": "{ misPedidos(primeros: 3) { id estado pago { estado } } }"}).json()
    finally:
        compose("start", "payments")
    assert len(r["data"]["misPedidos"]) > 0
    assert all(p["pago"] is None for p in r["data"]["misPedidos"])
    assert r["errors"][0]["path"][-1] == "pago"
    time.sleep(4)


# Sin verificar el correo no se puede ingresar (ni, por lo tanto, comprar)
def test_cliente_sin_verificar_no_ingresa():
    correo = f"sinverificar{random.randint(1000, 9999)}@gmail.com"
    datos = {
        "run": run_valido(), "nombre": "Cliente Sin Verificar", "correo": correo, "password": "Prueba2026!",
        "telefono": "+56955555555", "fecha_nacimiento": "2000-01-01", "sexo": "otro",
        "direccion": "Av. Providencia 1300", "comuna": "Providencia", "provincia": "Santiago", "region": "Metropolitana",
    }
    assert httpx.post(f"{BASE}/api/clientes/registro", json=datos).status_code == 201
    r = httpx.post(f"{BASE}/auth/login", json={"username": correo, "password": "Prueba2026!"})
    assert r.status_code == 403
    assert "session_token" not in r.cookies


# F. Logout: revoca la sesion en el Auth Service
def test_logout_revoca_la_sesion():
    cliente = ingresar("camila@aroma.cl")
    token = [c for c in cliente.cookies.jar if c.name == "session_token"][0].value
    assert cliente.post("/auth/logout").status_code == 200
    # Aunque alguien guardara el token, ya no sirve
    assert httpx.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
