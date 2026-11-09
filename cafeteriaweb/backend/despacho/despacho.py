import html
import os
import secrets
import unicodedata
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

# Configuracion
DB_NAME = os.getenv("DB_NAME", "aroma_despacho")
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")
ORDERS_URL = os.getenv("ORDERS_URL", "http://127.0.0.1:9200")

LLAMADORES = ["gateway", "graphql", "orders"]

# Despacho gratuito dentro de 3 km del local (Av. Siempreviva 123, Santiago).
# Sin un servicio de geocodificacion, el radio se aproxima con las comunas que
# quedan dentro de esa distancia.
COMUNAS_CUBIERTAS = ["santiago", "providencia", "recoleta", "independencia",
                     "estacion central", "quinta normal", "san miguel", "nunoa"]

# "Un par de choferes que utilizan sus vehiculos para las entregas"
CHOFERES = ["Chofer 1", "Chofer 2"]

# Estado de la orden de despacho -> estado que se informa al pedido
ESTADO_PEDIDO = {"en_preparacion": "en_preparacion", "en_ruta": "en_despacho", "entregada": "entregado"}
TRANSICIONES = {
    "pendiente": ["en_preparacion", "anulada"],
    "en_preparacion": ["en_ruta"],
    "en_ruta": ["entregada"],
    "entregada": [],
    "anulada": [],
}

client: AsyncIOMotorClient | None = None
db = None
SECRETOS = {}
SECRETO_ORDERS = ""


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
        entrantes[origen] = (await leer_vault(f"tramos/{origen}-despacho"))["secret"]
    saliente = (await leer_vault("tramos/despacho-orders"))["secret"]
    propios = await leer_vault("servicios/despacho")
    return {"mongodb_uri": propios["mongodb_uri"], "entrantes": entrantes, "orders": saliente}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db, SECRETOS, SECRETO_ORDERS
    config = await cargar_secretos()
    SECRETOS = config["entrantes"]
    SECRETO_ORDERS = config["orders"]
    client = AsyncIOMotorClient(config["mongodb_uri"], tz_aware=True)
    db = client[DB_NAME]
    await db.ordenes.create_index("numero", unique=True)
    yield
    client.close()


app = FastAPI(
    title="Despacho Service",
    description="Órdenes de despacho, cobertura y entregas de Aroma & Café",
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


async def avisar_orders(pedido_id, estado):
    try:
        async with httpx.AsyncClient(timeout=5.0) as cliente_http:
            return await cliente_http.post(
                f"{ORDERS_URL}/interno/pedidos/{pedido_id}/estado", json={"estado": estado},
                headers={"X-Service-Name": "despacho", "X-Service-Secret": SECRETO_ORDERS}
            )
    except httpx.RequestError:
        raise HTTPException(503, "Servicio orders no disponible")


def normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().split())


# Modelos
class ClienteDespacho(BaseModel):
    nombre: str
    correo: str
    direccion: str
    comuna: str
    telefono: str


class ItemDespacho(BaseModel):
    nombre: str
    cantidad: int


class OrdenIn(BaseModel):
    pedido_id: str
    cliente: ClienteDespacho
    items: List[ItemDespacho]


class EstadoIn(BaseModel):
    estado: str
    chofer: Optional[str] = None


class OrdenOut(BaseModel):
    pedido_id: str
    numero: int
    cliente: ClienteDespacho
    items: List[ItemDespacho]
    estado: str
    chofer: Optional[str] = None
    historial: List[dict]
    creado: datetime


def doc_to_ordenout(doc) -> OrdenOut:
    return OrdenOut(
        pedido_id=doc["_id"], numero=doc["numero"], cliente=doc["cliente"], items=doc["items"],
        estado=doc["estado"], chofer=doc.get("chofer"), historial=doc["historial"], creado=doc["creado"]
    )


async def buscar_orden(pedido_id):
    doc = await db.ordenes.find_one({"_id": pedido_id})
    if not doc:
        raise HTTPException(404, "Orden de despacho no encontrada")
    return doc


# EndPoints

@app.get("/health", tags=["sistema"])
def health():
    return {"status": "OK", "service": "Despacho Service"}


@app.get("/cobertura", tags=["cobertura"])
def cobertura(comuna: str = Query(min_length=2, max_length=60), origen=Depends(verificar_servicio("orders"))):
    return {"comuna": comuna, "cubierta": normalizar(comuna) in COMUNAS_CUBIERTAS}


# orders crea la orden cuando el pedido queda pagado. Idempotente por pedido.
@app.post("/ordenes", response_model=OrdenOut, status_code=201, tags=["interno"])
async def crear_orden(datos: OrdenIn, origen=Depends(verificar_servicio("orders"))):
    existente = await db.ordenes.find_one({"_id": datos.pedido_id})
    if existente:
        return doc_to_ordenout(existente)
    # Numero correlativo: el encargado atiende en orden de llegada
    contador = await db.contadores.find_one_and_update(
        {"_id": "ordenes"}, {"$inc": {"valor": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    ahora = datetime.now(timezone.utc)
    orden = {
        "_id": datos.pedido_id,
        "numero": contador["valor"],
        "cliente": datos.cliente.model_dump(),
        "items": [i.model_dump() for i in datos.items],
        "estado": "pendiente",
        "historial": [{"estado": "pendiente", "fecha": ahora, "por": "orders"}],
        "creado": ahora,
    }
    try:
        await db.ordenes.insert_one(orden)
    except DuplicateKeyError:
        return doc_to_ordenout(await buscar_orden(datos.pedido_id))
    return doc_to_ordenout(orden)


@app.post("/ordenes/{pedido_id}/anular", response_model=OrdenOut, tags=["interno"])
async def anular_orden(pedido_id: str, origen=Depends(verificar_servicio("orders"))):
    orden = await buscar_orden(pedido_id)
    if orden["estado"] == "anulada":
        return doc_to_ordenout(orden)
    if "anulada" not in TRANSICIONES[orden["estado"]]:
        raise HTTPException(409, "La orden ya está en preparación o despachada")
    orden = await db.ordenes.find_one_and_update(
        {"_id": pedido_id, "estado": orden["estado"]},
        {"$set": {"estado": "anulada"},
         "$push": {"historial": {"estado": "anulada", "fecha": datetime.now(timezone.utc), "por": "orders"}}},
        return_document=ReturnDocument.AFTER
    )
    return doc_to_ordenout(orden)


# Cola del encargado de despacho, en orden de llegada
@app.get("/ordenes", response_model=List[OrdenOut], tags=["encargado"])
async def listar_ordenes(
    estado: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "despacho", "admin")
    query = {"estado": estado} if estado else {"estado": {"$in": ["pendiente", "en_preparacion", "en_ruta"]}}
    ordenes = []
    async for doc in db.ordenes.find(query).sort("numero", 1).skip(skip).limit(limit):
        ordenes.append(doc_to_ordenout(doc))
    return ordenes


# Para GraphQL: ordenes de varios pedidos en una sola llamada (batching)
@app.get("/interno/ordenes", tags=["interno"])
async def ordenes_de_pedidos(pedido_ids: str = Query(max_length=2000), origen=Depends(verificar_servicio("graphql"))):
    ids = pedido_ids.split(",")[:100]
    resultado = {}
    async for doc in db.ordenes.find({"_id": {"$in": ids}}):
        resultado[doc["_id"]] = {"numero": doc["numero"], "estado": doc["estado"], "chofer": doc.get("chofer")}
    return resultado


@app.get("/ordenes/{pedido_id}", response_model=OrdenOut, tags=["encargado"])
async def obtener_orden(
    pedido_id: str,
    origen=Depends(verificar_servicio("gateway", "graphql")),
    usuario=Depends(identidad)
):
    if origen == "gateway":
        exigir_rol(usuario, "despacho", "admin")
    return doc_to_ordenout(await buscar_orden(pedido_id))


@app.patch("/ordenes/{pedido_id}/estado", response_model=OrdenOut, tags=["encargado"])
async def cambiar_estado(
    pedido_id: str,
    datos: EstadoIn,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "despacho")
    orden = await buscar_orden(pedido_id)
    if datos.estado not in ESTADO_PEDIDO or datos.estado not in TRANSICIONES[orden["estado"]]:
        raise HTTPException(409, f"No se puede pasar de {orden['estado']} a {datos.estado}")
    cambios = {"estado": datos.estado}
    if datos.estado == "en_ruta":
        if datos.chofer not in CHOFERES:
            raise HTTPException(422, f"Debe indicar un chofer: {', '.join(CHOFERES)}")
        cambios["chofer"] = datos.chofer

    # orders es el dueno del estado del pedido: si rechaza el cambio, no se aplica
    r = await avisar_orders(pedido_id, ESTADO_PEDIDO[datos.estado])
    if r.status_code != 200:
        raise HTTPException(409, "El pedido no admite ese cambio (¿fue anulado?)")

    orden = await db.ordenes.find_one_and_update(
        {"_id": pedido_id, "estado": orden["estado"]},
        {"$set": cambios,
         "$push": {"historial": {"estado": datos.estado, "fecha": datetime.now(timezone.utc),
                                 "por": usuario["user_id"]}}},
        return_document=ReturnDocument.AFTER
    )
    if orden is None:
        raise HTTPException(409, "La orden cambió de estado, intente nuevamente")
    return doc_to_ordenout(orden)


# RF 13: orden de despacho imprimible para cocina y chofer
@app.get("/ordenes/{pedido_id}/imprimir", response_class=HTMLResponse, tags=["encargado"])
async def imprimir_orden(
    pedido_id: str,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "despacho", "admin")
    o = await buscar_orden(pedido_id)
    e = html.escape
    filas = "".join(f"<tr><td>{i['cantidad']}</td><td>{e(i['nombre'])}</td></tr>" for i in o["items"])
    c = o["cliente"]
    chofer = f" — {e(o['chofer'])}" if o.get("chofer") else ""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Orden {o['numero']}</title>
<style>body{{font-family:sans-serif;max-width:420px;margin:2rem auto}}td{{padding:.2rem .5rem}}</style></head>
<body onload="window.print()"><h1>Aroma &amp; Café</h1><h2>Orden de despacho N° {o['numero']}</h2>
<p>Pedido {e(o['_id'])}<br>{o['creado'].strftime('%d-%m-%Y %H:%M')}</p>
<p><b>{e(c['nombre'])}</b><br>{e(c['direccion'])}, {e(c['comuna'])}<br>{e(c['telefono'])}</p>
<table><tr><th>Cant.</th><th>Producto</th></tr>{filas}</table>
<p>Estado: {e(o['estado'])}{chofer}</p></body></html>"""
