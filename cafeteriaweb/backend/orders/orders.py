import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

# Configuracion
DB_NAME = os.getenv("DB_NAME", "aroma_orders")
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")
URLS = {
    "inventory": os.getenv("INVENTORY_URL", "http://127.0.0.1:9100"),
    "clients": os.getenv("CLIENTS_URL", "http://127.0.0.1:9000"),
    "despacho": os.getenv("DESPACHO_URL", "http://127.0.0.1:9400"),
    "payments": os.getenv("PAYMENTS_URL", "http://127.0.0.1:9300"),
}

LLAMADORES = ["gateway", "graphql", "payments", "despacho"]
DESTINOS = ["inventory", "clients", "despacho", "payments"]

# Un pedido sin pagar retiene stock: se anula solo despues de este plazo
MINUTOS_PARA_PAGAR = 30

# Personal que puede consultar todos los pedidos
PERSONAL = ["admin", "cajero", "despacho", "dueno"]

# Ciclo de vida del pedido: estado actual -> estados siguientes permitidos
TRANSICIONES = {
    "pendiente_pago": ["pagado", "anulado"],
    "pagado": ["en_preparacion", "anulado"],
    "en_preparacion": ["en_despacho"],
    "en_despacho": ["entregado"],
    "entregado": [],
    "anulado": [],
}

client: AsyncIOMotorClient | None = None
db = None
SECRETOS = {}
SALIENTES = {}


async def leer_vault(ruta):
    async with httpx.AsyncClient(timeout=5.0) as cliente_http:
        response = await cliente_http.get(
            f"{VAULT_ADDR}/v1/secret/data/{ruta}",
            headers={"X-Vault-Token": VAULT_TOKEN}
        )
    if response.status_code != 200:
        raise RuntimeError(f"No fue posible leer {ruta} desde Vault")
    return response.json()["data"]["data"]


async def cargar_secretos():
    entrantes = {}
    for origen in LLAMADORES:
        entrantes[origen] = (await leer_vault(f"tramos/{origen}-orders"))["secret"]
    salientes = {}
    for destino in DESTINOS:
        salientes[destino] = (await leer_vault(f"tramos/orders-{destino}"))["secret"]
    propios = await leer_vault("servicios/orders")
    return {"mongodb_uri": propios["mongodb_uri"], "entrantes": entrantes, "salientes": salientes}


# Libera el stock de los pedidos que no se pagaron a tiempo
async def vencer_pendientes():
    limite = datetime.now(timezone.utc) - timedelta(minutes=MINUTOS_PARA_PAGAR)
    async for pedido in db.pedidos.find({"estado": "pendiente_pago", "creado": {"$lt": limite}}):
        try:
            await anular(pedido, "Pago no realizado dentro del plazo", "sistema")
        except HTTPException:
            pass


async def vencer_pedidos():
    while True:
        await vencer_pendientes()
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db, SECRETOS, SALIENTES
    config = await cargar_secretos()
    SECRETOS = config["entrantes"]
    SALIENTES = config["salientes"]
    client = AsyncIOMotorClient(config["mongodb_uri"], tz_aware=True)
    db = client[DB_NAME]
    await db.pedidos.create_index([("user_id", 1), ("creado", -1)])
    # Unico solo entre los pedidos que traen clave (un indice "sparse" compuesto
    # igual incluiria los pedidos sin clave, porque user_id siempre existe)
    if "user_id_1_clave_idempotencia_1" in await db.pedidos.index_information():
        await db.pedidos.drop_index("user_id_1_clave_idempotencia_1")
    await db.pedidos.create_index([("user_id", 1), ("clave_idempotencia", 1)], unique=True,
                                  name="idempotencia_por_cliente",
                                  partialFilterExpression={"clave_idempotencia": {"$exists": True}})
    tarea = asyncio.create_task(vencer_pedidos())
    yield
    tarea.cancel()
    client.close()


app = FastAPI(
    title="Orders Service",
    description="Pedidos y su ciclo de vida en Aroma & Café",
    lifespan=lifespan
)


def verificar_servicio(*permitidos):
    def verificar(
        x_service_name: str = Header(default=""),
        x_service_secret: str = Header(default="")
    ):
        esperado = SECRETOS.get(x_service_name)
        if (x_service_name not in permitidos or esperado is None
                or not secrets.compare_digest(x_service_secret, esperado)):
            raise HTTPException(status_code=403, detail="Solicitud no autorizada")
        return x_service_name
    return verificar


def identidad(
    x_authenticated_user: str | None = Header(default=None),
    x_authenticated_roles: str | None = Header(default=None)
):
    roles = x_authenticated_roles.split(",") if x_authenticated_roles else []
    return {"user_id": x_authenticated_user, "roles": roles}


def exigir_rol(usuario, *roles):
    if not any(rol in usuario["roles"] for rol in roles):
        raise HTTPException(status_code=403, detail="Permisos insuficientes")


async def llamar(destino, metodo, ruta, json=None, params=None):
    try:
        async with httpx.AsyncClient(timeout=5.0) as cliente_http:
            return await cliente_http.request(
                metodo, f"{URLS[destino]}{ruta}", json=json, params=params,
                headers={"X-Service-Name": "orders", "X-Service-Secret": SALIENTES[destino]}
            )
    except httpx.RequestError:
        raise HTTPException(503, f"Servicio {destino} no disponible")


# Modelos
class ItemPedido(BaseModel):
    producto_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    cantidad: int = Field(ge=1, le=50)


class PedidoIn(BaseModel):
    items: List[ItemPedido] = Field(min_length=1, max_length=30)


class AnularIn(BaseModel):
    motivo: str = Field(min_length=5, max_length=300)


class EstadoIn(BaseModel):
    estado: str


class PagadoIn(BaseModel):
    pago_id: str
    folio_boleta: int


class ItemOut(BaseModel):
    producto_id: str
    nombre: str
    precio: int
    cantidad: int
    subtotal: int


class PedidoOut(BaseModel):
    id: str
    user_id: str
    cliente: dict
    items: List[ItemOut]
    total: int
    estado: str
    historial: List[dict]
    motivo_anulacion: Optional[str] = None
    pago_id: Optional[str] = None
    folio_boleta: Optional[int] = None
    creado: datetime


def doc_to_pedidoout(doc) -> PedidoOut:
    return PedidoOut(
        id=doc["_id"],
        user_id=doc["user_id"],
        cliente=doc["cliente"],
        items=doc["items"],
        total=doc["total"],
        estado=doc["estado"],
        historial=doc["historial"],
        motivo_anulacion=doc.get("motivo_anulacion"),
        pago_id=doc.get("pago_id"),
        folio_boleta=doc.get("folio_boleta"),
        creado=doc["creado"],
    )


# El dueno ve pedidos y ventas, pero no los datos personales del cliente
VEN_DATOS_CLIENTE = ["admin", "cajero", "despacho"]


def para_usuario(usuario, pedido: PedidoOut) -> PedidoOut:
    if pedido.user_id != usuario["user_id"] and not any(r in usuario["roles"] for r in VEN_DATOS_CLIENTE):
        pedido.cliente = {}
    return pedido


def puede_ver(usuario, pedido) -> bool:
    return pedido["user_id"] == usuario["user_id"] or any(r in usuario["roles"] for r in PERSONAL)


async def buscar_pedido(pedido_id: str):
    pedido = await db.pedidos.find_one({"_id": pedido_id})
    if not pedido:
        raise HTTPException(404, "Pedido no encontrado")
    return pedido


# Cambia el estado solo si la transicion es valida y nadie lo cambio antes
async def cambiar_estado(pedido, nuevo, por, extra=None):
    if nuevo not in TRANSICIONES[pedido["estado"]]:
        raise HTTPException(409, f"No se puede pasar de {pedido['estado']} a {nuevo}")
    cambios = {"estado": nuevo}
    if extra:
        cambios.update(extra)
    res = await db.pedidos.find_one_and_update(
        {"_id": pedido["_id"], "estado": pedido["estado"]},
        {"$set": cambios,
         "$push": {"historial": {"estado": nuevo, "fecha": datetime.now(timezone.utc), "por": por}}},
        return_document=True
    )
    if res is None:
        raise HTTPException(409, "El pedido cambió de estado, intente nuevamente")
    return res


# Anular: no borra el pedido, guarda el motivo, devuelve el stock y,
# si ya estaba pagado, pide la devolucion del pago y cancela el despacho.
# Si estaba pagado, primero se devuelve el dinero y se cancela el despacho: si
# alguno falla, el pedido sigue pagado y se puede reintentar (no queda anulado sin reembolso).
async def anular(pedido, motivo, por):
    if "anulado" not in TRANSICIONES[pedido["estado"]]:
        raise HTTPException(409, f"No se puede pasar de {pedido['estado']} a anulado")
    if pedido["estado"] == "pagado":
        r = await llamar("despacho", "POST", f"/ordenes/{pedido['_id']}/anular")
        # 404: la orden de despacho aun no se habia creado, no hay nada que cancelar
        if r.status_code not in (200, 404):
            raise HTTPException(409, "La orden de despacho ya está en preparación")
        r = await llamar("payments", "POST", f"/interno/pagos/pedido/{pedido['_id']}/reembolsar")
        if r.status_code != 200:
            raise HTTPException(502, "No fue posible devolver el pago; el pedido sigue pagado")
    pedido = await cambiar_estado(pedido, "anulado", por, {"motivo_anulacion": motivo})
    await llamar("inventory", "POST", f"/reservas/{pedido['_id']}/liberar")
    return pedido


# EndPoints

@app.get("/health", tags=["sistema"])
def health():
    return {"status": "OK", "service": "Orders Service"}


# RF 1: el cliente arma un pedido con productos disponibles. El precio y el
# total los calcula el servidor con los datos de inventory.
@app.post("/pedidos", response_model=PedidoOut, status_code=201, tags=["pedidos"])
async def crear_pedido(
    datos: PedidoIn,
    idempotency_key: Optional[str] = Header(default=None, max_length=64),
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "cliente")

    # Un doble clic con la misma clave devuelve el mismo pedido
    if idempotency_key:
        existente = await db.pedidos.find_one({"user_id": usuario["user_id"], "clave_idempotencia": idempotency_key})
        if existente:
            return doc_to_pedidoout(existente)

    # RF 4: solo clientes registrados y verificados
    r = await llamar("clients", "GET", f"/interno/clientes/{usuario['user_id']}")
    if r.status_code != 200:
        raise HTTPException(403, "El cliente no está registrado o no verificó su correo")
    cliente = r.json()

    # Despacho gratuito solo dentro del radio de cobertura
    r = await llamar("despacho", "GET", "/cobertura", params={"comuna": cliente["comuna"]})
    if r.status_code != 200:
        raise HTTPException(502, "No fue posible validar la cobertura de despacho")
    if not r.json()["cubierta"]:
        raise HTTPException(422, f"No hay despacho a {cliente['comuna']}.")

    pedido_id = "PED-" + secrets.token_hex(4).upper()
    r = await llamar("inventory", "POST", "/reservas", json={
        "pedido_id": pedido_id,
        "items": [{"producto_id": i.producto_id, "cantidad": i.cantidad} for i in datos.items]
    })
    if r.status_code == 409:
        raise HTTPException(409, "No hay stock suficiente para uno o más productos")
    if r.status_code != 201:
        raise HTTPException(502, "No fue posible reservar el stock")

    items = [dict(i, subtotal=i["precio"] * i["cantidad"]) for i in r.json()["items"]]
    ahora = datetime.now(timezone.utc)
    pedido = {
        "_id": pedido_id,
        "user_id": usuario["user_id"],
        "cliente": {k: cliente[k] for k in ("nombre", "correo", "direccion", "comuna", "telefono")},
        "items": items,
        "total": sum(i["subtotal"] for i in items),
        "estado": "pendiente_pago",
        "historial": [{"estado": "pendiente_pago", "fecha": ahora, "por": usuario["user_id"]}],
        "creado": ahora,
    }
    if idempotency_key:
        pedido["clave_idempotencia"] = idempotency_key
    try:
        await db.pedidos.insert_one(pedido)
    except DuplicateKeyError:
        await llamar("inventory", "POST", f"/reservas/{pedido_id}/liberar")
        return doc_to_pedidoout(await db.pedidos.find_one(
            {"user_id": usuario["user_id"], "clave_idempotencia": idempotency_key}))
    return doc_to_pedidoout(pedido)


@app.get("/pedidos/mios", response_model=List[PedidoOut], tags=["pedidos"])
async def mis_pedidos(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "cliente")
    pedidos = []
    async for doc in db.pedidos.find({"user_id": usuario["user_id"]}).sort("creado", -1).skip(skip).limit(limit):
        pedidos.append(doc_to_pedidoout(doc))
    return pedidos


@app.get("/pedidos", response_model=List[PedidoOut], tags=["pedidos"])
async def listar_pedidos(
    estado: Optional[str] = Query(None),
    desde: Optional[datetime] = Query(None),
    hasta: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, *PERSONAL)
    query = {}
    if estado:
        if estado not in TRANSICIONES:
            raise HTTPException(422, "Estado invalido")
        query["estado"] = estado
    if desde or hasta:
        query["creado"] = {}
        if desde:
            query["creado"]["$gte"] = desde
        if hasta:
            query["creado"]["$lte"] = hasta
    pedidos = []
    async for doc in db.pedidos.find(query).sort("creado", -1).skip(skip).limit(limit):
        pedidos.append(para_usuario(usuario, doc_to_pedidoout(doc)))
    return pedidos


@app.get("/pedidos/{pedido_id}", response_model=PedidoOut, tags=["pedidos"])
async def obtener_pedido(
    pedido_id: str,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    pedido = await buscar_pedido(pedido_id)
    # Un cliente solo ve sus pedidos; se responde 404 para no revelar pedidos ajenos
    if not puede_ver(usuario, pedido):
        raise HTTPException(404, "Pedido no encontrado")
    return para_usuario(usuario, doc_to_pedidoout(pedido))


# RF 3: anulacion con motivo, por el cliente (sus pedidos) o el administrador
@app.post("/pedidos/{pedido_id}/anular", response_model=PedidoOut, tags=["pedidos"])
async def anular_pedido(
    pedido_id: str,
    datos: AnularIn,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    pedido = await buscar_pedido(pedido_id)
    es_admin = "admin" in usuario["roles"]
    if not es_admin and pedido["user_id"] != usuario["user_id"]:
        raise HTTPException(404, "Pedido no encontrado")
    return doc_to_pedidoout(await anular(pedido, datos.motivo, usuario["user_id"]))


# Uso interno

# payments confirma el pago: recien ahi el pedido pasa a preparacion (RF 2)
@app.post("/interno/pedidos/{pedido_id}/pagado", response_model=PedidoOut, tags=["interno"])
async def marcar_pagado(pedido_id: str, datos: PagadoIn, origen=Depends(verificar_servicio("payments"))):
    pedido = await buscar_pedido(pedido_id)
    # Si payments reintenta, no se cambia el estado otra vez, pero si se
    # asegura la orden de despacho (crearla en despacho es idempotente)
    if not (pedido["estado"] == "pagado" and pedido.get("pago_id") == datos.pago_id):
        pedido = await cambiar_estado(pedido, "pagado", "payments",
                                      {"pago_id": datos.pago_id, "folio_boleta": datos.folio_boleta})
    # Orden de despacho para el encargado (RF 13)
    r = await llamar("despacho", "POST", "/ordenes", json={
        "pedido_id": pedido["_id"],
        "cliente": pedido["cliente"],
        "items": [{"nombre": i["nombre"], "cantidad": i["cantidad"]} for i in pedido["items"]],
    })
    if r.status_code not in (200, 201):
        raise HTTPException(502, "No fue posible crear la orden de despacho")
    return doc_to_pedidoout(pedido)


# despacho informa el avance de la preparacion y la entrega
@app.post("/interno/pedidos/{pedido_id}/estado", response_model=PedidoOut, tags=["interno"])
async def avanzar_estado(pedido_id: str, datos: EstadoIn, origen=Depends(verificar_servicio("despacho"))):
    if datos.estado not in ("en_preparacion", "en_despacho", "entregado"):
        raise HTTPException(422, "Estado invalido para despacho")
    pedido = await buscar_pedido(pedido_id)
    if pedido["estado"] == datos.estado:
        return doc_to_pedidoout(pedido)
    return doc_to_pedidoout(await cambiar_estado(pedido, datos.estado, "despacho"))


@app.get("/interno/pedidos/{pedido_id}", response_model=PedidoOut, tags=["interno"])
async def pedido_interno(pedido_id: str, origen=Depends(verificar_servicio("payments", "graphql"))):
    return doc_to_pedidoout(await buscar_pedido(pedido_id))


# Para GraphQL: pedidos de un usuario o de un periodo, en una sola llamada
@app.get("/interno/pedidos", response_model=List[PedidoOut], tags=["interno"])
async def pedidos_interno(
    user_id: Optional[str] = Query(None),
    desde: Optional[datetime] = Query(None),
    hasta: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    origen=Depends(verificar_servicio("graphql"))
):
    query = {}
    if user_id:
        query["user_id"] = user_id
    if desde or hasta:
        query["creado"] = {}
        if desde:
            query["creado"]["$gte"] = desde
        if hasta:
            query["creado"]["$lte"] = hasta
    pedidos = []
    async for doc in db.pedidos.find(query).sort("creado", -1).skip(skip).limit(limit):
        pedidos.append(doc_to_pedidoout(doc))
    return pedidos
