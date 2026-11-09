import asyncio
import hashlib
import hmac
import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

# Configuracion
DB_NAME = os.getenv("DB_NAME", "aroma_payments")
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")
URLS = {
    "orders": os.getenv("ORDERS_URL", "http://127.0.0.1:9200"),
    "mensajeria": os.getenv("MENSAJERIA_URL", "http://127.0.0.1:9600"),
}
PROVEEDOR_URL = os.getenv("PROVEEDOR_URL", "http://127.0.0.1:9500")
# A donde vuelve el navegador despues de pagar
URL_RETORNO = os.getenv("URL_RETORNO", "http://localhost:8000/api/pedidos/mios")

LLAMADORES = ["gateway", "orders", "graphql"]
DESTINOS = ["orders", "mensajeria"]

# RF 4: las ventas web se asocian a una caja de un cajero virtual
CAJA = {"id": "CAJA-WEB-01", "cajero_virtual": "Cajero virtual web"}
IVA = 0.19
# Un aviso del proveedor con mas antiguedad que esto se rechaza (reenvio malicioso)
MINUTOS_VALIDEZ_AVISO = 10

PERSONAL_VENTAS = ["cajero", "admin", "dueno"]

client: AsyncIOMotorClient | None = None
db = None
SECRETOS = {}
SALIENTES = {}
PROVEEDOR = {}


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
        entrantes[origen] = (await leer_vault(f"tramos/{origen}-payments"))["secret"]
    salientes = {}
    for destino in DESTINOS:
        salientes[destino] = (await leer_vault(f"tramos/payments-{destino}"))["secret"]
    propios = await leer_vault("servicios/payments")
    return {
        "mongodb_uri": propios["mongodb_uri"],
        "entrantes": entrantes,
        "salientes": salientes,
        "proveedor": {"api_key": propios["proveedor_api_key"], "clave_firma": propios["proveedor_clave_firma"]},
    }


async def reintentar_pendientes():
    # Si orders no respondio al confirmar un pago, se reintenta cada minuto
    while True:
        await asyncio.sleep(60)
        async for pago in db.pagos.find({"estado": "aprobado", "pedido_notificado": False}):
            try:
                await confirmar_en_orders(pago)
            except HTTPException:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db, SECRETOS, SALIENTES, PROVEEDOR
    config = await cargar_secretos()
    SECRETOS = config["entrantes"]
    SALIENTES = config["salientes"]
    PROVEEDOR = config["proveedor"]
    client = AsyncIOMotorClient(config["mongodb_uri"], tz_aware=True)
    db = client[DB_NAME]
    await db.pagos.create_index("pedido_id")
    await db.boletas.create_index("pedido_id")
    await db.boletas.create_index("pago_id", unique=True)
    await db.ventas.create_index("fecha")
    tarea = asyncio.create_task(reintentar_pendientes())
    yield
    tarea.cancel()
    client.close()


app = FastAPI(
    title="Payments Service",
    description="Pagos, ventas de la caja web y boletas de Aroma & Café",
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


async def llamar(destino, metodo, ruta, json=None):
    try:
        async with httpx.AsyncClient(timeout=5.0) as cliente_http:
            return await cliente_http.request(
                metodo, f"{URLS[destino]}{ruta}", json=json,
                headers={"X-Service-Name": "payments", "X-Service-Secret": SALIENTES[destino]}
            )
    except httpx.RequestError:
        raise HTTPException(503, f"Servicio {destino} no disponible")


async def llamar_proveedor(metodo, ruta, json=None):
    try:
        async with httpx.AsyncClient(timeout=10.0) as cliente_http:
            return await cliente_http.request(metodo, f"{PROVEEDOR_URL}{ruta}", json=json,
                                              headers={"X-Api-Key": PROVEEDOR["api_key"]})
    except httpx.RequestError:
        raise HTTPException(503, "Plataforma de pago no disponible")


# Modelos
class PagoIn(BaseModel):
    pedido_id: str = Field(min_length=1, max_length=20)


class PagoOut(BaseModel):
    id: str
    pedido_id: str
    monto: int
    estado: str
    url_pago: Optional[str] = None
    creado: datetime


def doc_to_pagoout(doc) -> PagoOut:
    return PagoOut(id=doc["_id"], pedido_id=doc["pedido_id"], monto=doc["monto"], estado=doc["estado"],
                   url_pago=doc.get("url_pago") if doc["estado"] == "iniciado" else None, creado=doc["creado"])


def boleta_out(doc):
    return {
        "folio": doc["_id"], "pedido_id": doc["pedido_id"], "fecha": doc["fecha"].isoformat(),
        "caja": doc["caja"], "cliente": doc["cliente"], "items": doc["items"],
        "neto": doc["neto"], "iva": doc["iva"], "total": doc["total"],
        "anulada": doc["anulada"], "enviada": doc["enviada"],
    }


def pesos(valor: int) -> str:
    return f"${valor:,}".replace(",", ".")


def texto_boleta(b) -> str:
    lineas = [f"{i['cantidad']} x {i['nombre']}  {pesos(i['subtotal'])}" for i in b["items"]]
    return "\n".join([
        f"Aroma & Café — Boleta electrónica N° {b['_id']}",
        f"Fecha: {b['fecha'].strftime('%d-%m-%Y %H:%M')}  Caja: {b['caja']['id']}",
        f"Cliente: {b['cliente']['nombre']}",
        "", *lineas, "",
        f"Neto: {pesos(b['neto'])}",
        f"IVA (19%): {pesos(b['iva'])}",
        f"Total: {pesos(b['total'])}",
    ])


async def enviar_boleta(boleta):
    r = await llamar("mensajeria", "POST", "/enviar", {
        "para": boleta["cliente"]["correo"],
        "asunto": f"Aroma & Café: boleta N° {boleta['_id']}",
        "cuerpo": texto_boleta(boleta),
    })
    if r.status_code == 202:
        await db.boletas.update_one({"_id": boleta["_id"]}, {"$set": {"enviada": True}})


# Venta y boleta (RF 4 y 8). Idempotente: una sola venta y boleta por pago.
async def registrar_venta(pago):
    existente = await db.boletas.find_one({"pago_id": pago["_id"]})
    if existente:
        return existente
    r = await llamar("orders", "GET", f"/interno/pedidos/{pago['pedido_id']}")
    if r.status_code != 200:
        raise HTTPException(502, "No fue posible leer el pedido")
    pedido = r.json()
    ahora = datetime.now(timezone.utc)
    contador = await db.contadores.find_one_and_update(
        {"_id": "boletas"}, {"$inc": {"valor": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    neto = round(pedido["total"] / (1 + IVA))
    boleta = {
        "_id": contador["valor"],
        "pago_id": pago["_id"],
        "pedido_id": pedido["id"],
        "user_id": pedido["user_id"],
        "fecha": ahora,
        "caja": CAJA,
        "cliente": {"nombre": pedido["cliente"]["nombre"], "correo": pedido["cliente"]["correo"]},
        "items": [{"nombre": i["nombre"], "cantidad": i["cantidad"], "precio": i["precio"],
                   "subtotal": i["subtotal"]} for i in pedido["items"]],
        "neto": neto,
        "iva": pedido["total"] - neto,
        "total": pedido["total"],
        "anulada": False,
        "enviada": False,
    }
    try:
        await db.boletas.insert_one(boleta)
    except DuplicateKeyError:
        return await db.boletas.find_one({"pago_id": pago["_id"]})
    await db.ventas.insert_one({
        "_id": "VTA-" + pago["_id"], "pago_id": pago["_id"], "pedido_id": pedido["id"], "folio": boleta["_id"],
        "caja": CAJA, "total": pedido["total"], "items": boleta["items"], "fecha": ahora, "anulada": False,
    })
    await enviar_boleta(boleta)
    return boleta


async def reembolsar(pago):
    r = await llamar_proveedor("POST", f"/transacciones/{pago['token']}/reembolso")
    if r.status_code != 200:
        raise HTTPException(502, "La plataforma de pago no confirmó la devolución")
    await db.pagos.update_one({"_id": pago["_id"]}, {"$set": {"estado": "reembolsado"}})
    await db.ventas.update_one({"pago_id": pago["_id"]}, {"$set": {"anulada": True}})
    await db.boletas.update_one({"pago_id": pago["_id"]}, {"$set": {"anulada": True}})


# Registra la venta (si falta) y le informa a orders que el pedido esta pagado
async def confirmar_en_orders(pago):
    boleta = await registrar_venta(pago)
    r = await llamar("orders", "POST", f"/interno/pedidos/{pago['pedido_id']}/pagado",
                     {"pago_id": pago["_id"], "folio_boleta": boleta["_id"]})
    if r.status_code == 200:
        await db.pagos.update_one({"_id": pago["_id"]}, {"$set": {"pedido_notificado": True}})
        return boleta
    if r.status_code == 409:
        # El pedido ya no admite el pago (por ejemplo, vencio y se anulo): se devuelve el dinero
        await db.pagos.update_one({"_id": pago["_id"]}, {"$set": {"pedido_notificado": True}})
        await reembolsar(pago)
        return boleta
    raise HTTPException(502, "orders no confirmó el pago")


# EndPoints

@app.get("/health", tags=["sistema"])
def health():
    return {"status": "OK", "service": "Payments Service"}


@app.post("/pagos", response_model=PagoOut, status_code=201, tags=["pagos"])
async def iniciar_pago(datos: PagoIn, origen=Depends(verificar_servicio("gateway")), usuario=Depends(identidad)):
    exigir_rol(usuario, "cliente")
    r = await llamar("orders", "GET", f"/interno/pedidos/{datos.pedido_id}")
    if r.status_code != 200:
        raise HTTPException(404, "Pedido no encontrado")
    pedido = r.json()
    if pedido["user_id"] != usuario["user_id"]:
        raise HTTPException(404, "Pedido no encontrado")
    if pedido["estado"] != "pendiente_pago":
        raise HTTPException(409, "El pedido no está pendiente de pago")

    # Si ya hay un intento abierto se reutiliza (evita cobrar dos veces)
    abierto = await db.pagos.find_one({"pedido_id": pedido["id"], "estado": "iniciado"})
    if abierto:
        return doc_to_pagoout(abierto)

    pago_id = "PAG-" + secrets.token_hex(5).upper()
    # El monto sale del pedido calculado por el servidor, nunca del navegador
    r = await llamar_proveedor("POST", "/transacciones", {
        "referencia": pago_id, "monto": pedido["total"],
        "url_retorno": f"{URL_RETORNO}?pedido={pedido['id']}",
    })
    if r.status_code != 201:
        raise HTTPException(502, "La plataforma de pago rechazó la transacción")
    pago = {
        "_id": pago_id, "pedido_id": pedido["id"], "user_id": usuario["user_id"], "monto": pedido["total"],
        "estado": "iniciado", "token": r.json()["token"], "url_pago": r.json()["url_pago"],
        "pedido_notificado": False, "creado": datetime.now(timezone.utc),
    }
    await db.pagos.insert_one(pago)
    return doc_to_pagoout(pago)


@app.get("/pagos/{pago_id}", response_model=PagoOut, tags=["pagos"])
async def obtener_pago(pago_id: str, origen=Depends(verificar_servicio("gateway")), usuario=Depends(identidad)):
    pago = await db.pagos.find_one({"_id": pago_id})
    if not pago or (pago["user_id"] != usuario["user_id"]
                    and not any(r in usuario["roles"] for r in PERSONAL_VENTAS)):
        raise HTTPException(404, "Pago no encontrado")
    return doc_to_pagoout(pago)


# Aviso de la plataforma de pago. Llega por el gateway como ruta publica, por eso
# la autenticidad se comprueba con la firma HMAC del proveedor.
@app.post("/notificaciones", tags=["proveedor"])
async def notificacion(
    request: Request,
    x_firma: str = Header(default=""),
    origen=Depends(verificar_servicio("gateway"))
):
    cuerpo = await request.body()
    esperada = hmac.new(PROVEEDOR["clave_firma"].encode(), cuerpo, hashlib.sha256).hexdigest()
    if not secrets.compare_digest(x_firma, esperada):
        raise HTTPException(401, "Firma invalida")
    evento = json.loads(cuerpo)
    fecha = datetime.fromisoformat(evento["fecha"])
    if datetime.now(timezone.utc) - fecha > timedelta(minutes=MINUTOS_VALIDEZ_AVISO):
        raise HTTPException(400, "Aviso vencido")

    pago = await db.pagos.find_one({"_id": evento["referencia"], "token": evento["token"]})
    if not pago:
        raise HTTPException(404, "Pago no encontrado")
    if evento["monto"] != pago["monto"]:
        raise HTTPException(400, "El monto no coincide con el pago")

    # Idempotencia: cada evento del proveedor se procesa una sola vez
    try:
        await db.eventos.insert_one({"_id": evento["evento_id"], "pago_id": pago["_id"],
                                     "estado": evento["estado"], "recibido": datetime.now(timezone.utc)})
    except DuplicateKeyError:
        # Si el primer intento quedo a medias, se completa sin repetir la venta
        if pago["estado"] == "aprobado" and not pago["pedido_notificado"]:
            await confirmar_en_orders(pago)
        return {"resultado": "duplicado"}

    if evento["estado"] == "rechazado":
        await db.pagos.update_one({"_id": pago["_id"], "estado": "iniciado"}, {"$set": {"estado": "rechazado"}})
        return {"resultado": "rechazado"}
    if evento["estado"] != "aprobado":
        return {"resultado": "ignorado"}

    pago = await db.pagos.find_one_and_update(
        {"_id": pago["_id"], "estado": "iniciado"}, {"$set": {"estado": "aprobado"}},
        return_document=ReturnDocument.AFTER
    )
    if pago is None:
        return {"resultado": "sin cambios"}
    boleta = await confirmar_en_orders(pago)
    return {"resultado": "aprobado", "folio": boleta["_id"]}


@app.get("/boletas/pedido/{pedido_id}", tags=["boletas"])
async def boleta_de_pedido(pedido_id: str, origen=Depends(verificar_servicio("gateway")), usuario=Depends(identidad)):
    boleta = await db.boletas.find_one({"pedido_id": pedido_id}, sort=[("_id", -1)])
    if not boleta or (boleta["user_id"] != usuario["user_id"]
                      and not any(r in usuario["roles"] for r in PERSONAL_VENTAS)):
        raise HTTPException(404, "Boleta no encontrada")
    return boleta_out(boleta)


# La emision la hace el cajero virtual; tambien puede reenviarla
@app.post("/boletas/{folio}/reenviar", tags=["boletas"])
async def reenviar_boleta(folio: int, origen=Depends(verificar_servicio("gateway")), usuario=Depends(identidad)):
    exigir_rol(usuario, "cajero", "admin")
    boleta = await db.boletas.find_one({"_id": folio})
    if not boleta:
        raise HTTPException(404, "Boleta no encontrada")
    await enviar_boleta(boleta)
    return {"message": f"Boleta {folio} reenviada a {boleta['cliente']['correo']}"}


@app.get("/ventas", tags=["ventas"])
async def listar_ventas(
    desde: Optional[datetime] = Query(None),
    hasta: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    origen=Depends(verificar_servicio("gateway", "graphql")),
    usuario=Depends(identidad)
):
    if origen == "gateway":
        exigir_rol(usuario, *PERSONAL_VENTAS)
    query = {}
    if desde or hasta:
        query["fecha"] = {}
        if desde:
            query["fecha"]["$gte"] = desde
        if hasta:
            query["fecha"]["$lte"] = hasta
    ventas = []
    async for v in db.ventas.find(query).sort("fecha", -1).skip(skip).limit(limit):
        ventas.append({"id": v["_id"], "pedido_id": v["pedido_id"], "folio": v["folio"], "caja": v["caja"]["id"],
                       "total": v["total"], "items": v["items"], "fecha": v["fecha"].isoformat(),
                       "anulada": v["anulada"]})
    return ventas


# Uso interno

@app.post("/interno/pagos/pedido/{pedido_id}/reembolsar", tags=["interno"])
async def reembolsar_pedido(pedido_id: str, origen=Depends(verificar_servicio("orders"))):
    pago = await db.pagos.find_one({"pedido_id": pedido_id, "estado": {"$in": ["aprobado", "reembolsado"]}})
    if not pago:
        raise HTTPException(404, "El pedido no tiene un pago aprobado")
    if pago["estado"] == "aprobado":
        await reembolsar(pago)
    return {"pedido_id": pedido_id, "estado": "reembolsado"}


# Para GraphQL: estado de pago de varios pedidos en una sola llamada (batching)
@app.get("/interno/pagos", tags=["interno"])
async def pagos_de_pedidos(pedido_ids: str = Query(max_length=2000), origen=Depends(verificar_servicio("graphql"))):
    ids = pedido_ids.split(",")[:100]
    resultado = {}
    async for pago in db.pagos.find({"pedido_id": {"$in": ids}}).sort("creado", 1):
        # Queda el ultimo intento de cada pedido
        resultado[pago["pedido_id"]] = {"id": pago["_id"], "estado": pago["estado"], "monto": pago["monto"]}
    async for boleta in db.boletas.find({"pedido_id": {"$in": ids}}):
        if boleta["pedido_id"] in resultado:
            resultado[boleta["pedido_id"]]["folio_boleta"] = boleta["_id"]
    return resultado
