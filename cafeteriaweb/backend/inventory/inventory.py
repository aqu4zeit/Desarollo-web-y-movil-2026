import os
import secrets
from contextlib import asynccontextmanager
from typing import List, Optional

import httpx
from bson import ObjectId
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

# Configuracion
DB_NAME = os.getenv("DB_NAME", "aroma_inventory")
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")

# Servicios que pueden llamar a inventory: cada uno con su propio secreto en Vault
# (secret/tramos/<origen>-inventory).
LLAMADORES = ["gateway", "graphql", "orders"]

client: AsyncIOMotorClient | None = None
db = None
SECRETOS = {}


async def leer_vault(ruta):
    async with httpx.AsyncClient(timeout=5.0) as cliente_http:
        response = await cliente_http.get(
            f"{VAULT_ADDR}/v1/secret/data/{ruta}",
            headers={"X-Vault-Token": VAULT_TOKEN}
        )
    if response.status_code != 200:
        raise RuntimeError(f"No fue posible leer {ruta} desde Vault")
    return response.json()["data"]["data"]


# Lee de Vault la URI de su base (usuario propio de Mongo) y los secretos de
# quienes lo llaman.
async def cargar_secretos():
    entrantes = {}
    for origen in LLAMADORES:
        entrantes[origen] = (await leer_vault(f"tramos/{origen}-inventory"))["secret"]
    propios = await leer_vault("servicios/inventory")
    return {"mongodb_uri": propios["mongodb_uri"], "entrantes": entrantes}


# Datos de prueba: el mismo catalogo que tenia app.js
CATEGORIAS_INICIALES = [
    {"_id": 1, "nombre": "Cafés"},
    {"_id": 2, "nombre": "Bebidas frías"},
    {"_id": 3, "nombre": "Pastelería"},
]

PRODUCTOS_INICIALES = [
    {"categoria_id": 1, "nombre": "Espresso", "descripcion": "Shot intenso de café de especialidad.", "precio": 2200, "destacado": True, "imagen": "https://images.unsplash.com/photo-1705952285570-113e76f63fb0?w=120&h=120&fit=crop&q=80"},
    {"categoria_id": 1, "nombre": "Cappuccino", "descripcion": "Espresso con leche vaporizada y espuma.", "precio": 3200, "destacado": True, "imagen": "https://images.unsplash.com/photo-1572442388796-11668a67e53d?w=120&h=120&fit=crop&q=80"},
    {"categoria_id": 1, "nombre": "Flat White", "descripcion": "Doble espresso con leche sedosa.", "precio": 3400, "destacado": False, "imagen": None},
    {"categoria_id": 1, "nombre": "Filtrado V60", "descripcion": "Método manual que resalta notas del grano.", "precio": 3600, "destacado": False, "imagen": None},
    {"categoria_id": 2, "nombre": "Cold Brew", "descripcion": "Café extraído en frío durante 18 horas.", "precio": 3500, "destacado": True, "imagen": "https://images.unsplash.com/photo-1625126590447-cb769384e1f0?w=120&h=120&fit=crop&q=80"},
    {"categoria_id": 2, "nombre": "Latte helado", "descripcion": "Espresso, leche y hielo.", "precio": 3300, "destacado": False, "imagen": None},
    {"categoria_id": 3, "nombre": "Croissant", "descripcion": "Hojaldre de mantequilla horneado cada mañana.", "precio": 2500, "destacado": False, "imagen": None},
    {"categoria_id": 3, "nombre": "Cheesecake", "descripcion": "Con salsa de frutos rojos.", "precio": 3800, "destacado": False, "imagen": None},
]


async def cargar_datos_iniciales():
    if await db.categorias.count_documents({}) == 0:
        await db.categorias.insert_many(CATEGORIAS_INICIALES)
    if await db.productos.count_documents({}) == 0:
        await db.productos.insert_many(
            [dict(p, stock=30, activo=True) for p in PRODUCTOS_INICIALES]
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db, SECRETOS
    config = await cargar_secretos()
    SECRETOS = config["entrantes"]
    client = AsyncIOMotorClient(config["mongodb_uri"])
    db = client[DB_NAME]
    await cargar_datos_iniciales()
    yield
    client.close()


app = FastAPI(
    title="Inventory Service",
    description="Productos, categorías, precios y stock de Aroma & Café",
    lifespan=lifespan
)


# Seguridad: el servicio solo acepta llamadas de los servicios autorizados
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


# Identidad del usuario propagada por el gateway despues de validar la sesion
def identidad(
    x_authenticated_user: str | None = Header(default=None),
    x_authenticated_roles: str | None = Header(default=None)
):
    roles = x_authenticated_roles.split(",") if x_authenticated_roles else []
    return {"user_id": x_authenticated_user, "roles": roles}


def exigir_rol(usuario, *roles):
    if not any(rol in usuario["roles"] for rol in roles):
        raise HTTPException(status_code=403, detail="Permisos insuficientes")


# Modelos
class Categoria(BaseModel):
    id: int
    nombre: str


class ProductoIn(BaseModel):
    categoria_id: int = Field(ge=1)
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str = Field(min_length=1, max_length=300)
    precio: int = Field(gt=0, le=1000000, description="Precio en pesos chilenos")
    stock: int = Field(ge=0, le=10000)
    destacado: bool = False
    imagen: Optional[str] = Field(default=None, max_length=500)
    activo: bool = True


class ProductoOut(ProductoIn):
    id: str
    disponible: bool


class StockIn(BaseModel):
    stock: int = Field(ge=0, le=10000)
    activo: bool = True


class ItemReserva(BaseModel):
    producto_id: str
    cantidad: int = Field(ge=1, le=50)


class ReservaIn(BaseModel):
    pedido_id: str = Field(min_length=1)
    items: List[ItemReserva] = Field(min_length=1, max_length=30)


def doc_to_productoout(doc) -> ProductoOut:
    return ProductoOut(
        id=str(doc["_id"]),
        categoria_id=doc["categoria_id"],
        nombre=doc["nombre"],
        descripcion=doc["descripcion"],
        precio=doc["precio"],
        stock=doc["stock"],
        destacado=doc.get("destacado", False),
        imagen=doc.get("imagen"),
        activo=doc.get("activo", True),
        disponible=doc.get("activo", True) and doc["stock"] > 0,
    )


def object_id(valor: str) -> ObjectId:
    if not ObjectId.is_valid(valor):
        raise HTTPException(400, "id invalido")
    return ObjectId(valor)


# EndPoints

@app.get("/health", tags=["sistema"])
def health():
    return {"status": "OK", "service": "Inventory Service"}


@app.get("/categorias", response_model=List[Categoria], tags=["catalogo"])
async def listar_categorias(origen=Depends(verificar_servicio("gateway", "graphql"))):
    categorias = []
    async for doc in db.categorias.find().sort("_id", 1):
        categorias.append(Categoria(id=doc["_id"], nombre=doc["nombre"]))
    return categorias


@app.get("/productos", response_model=List[ProductoOut], tags=["catalogo"])
async def listar_productos(
    categoria_id: Optional[int] = Query(None),
    q: Optional[str] = Query(None, max_length=50, description="Filtro por nombre"),
    ids: Optional[str] = Query(None, description="Lista de ids separados por coma"),
    incluir_inactivos: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    origen=Depends(verificar_servicio("gateway", "graphql", "orders")),
    usuario=Depends(identidad)
):
    query = {}
    if categoria_id is not None:
        query["categoria_id"] = categoria_id
    if q:
        query["nombre"] = {"$regex": q, "$options": "i"}
    if ids:
        query["_id"] = {"$in": [object_id(i) for i in ids.split(",")]}
    # Solo el administrador ve los productos dados de baja
    if not (incluir_inactivos and "admin" in usuario["roles"]) and not ids:
        query["activo"] = True
    cursor = db.productos.find(query).sort("categoria_id", 1).skip(skip).limit(limit)
    productos: List[ProductoOut] = []
    async for doc in cursor:
        productos.append(doc_to_productoout(doc))
    return productos


@app.get("/productos/{producto_id}", response_model=ProductoOut, tags=["catalogo"])
async def obtener_producto(
    producto_id: str,
    origen=Depends(verificar_servicio("gateway", "graphql", "orders"))
):
    doc = await db.productos.find_one({"_id": object_id(producto_id)})
    if not doc:
        raise HTTPException(404, "Producto no encontrado")
    return doc_to_productoout(doc)


@app.post("/productos", response_model=ProductoOut, status_code=201, tags=["mantenedor"])
async def crear_producto(
    producto: ProductoIn,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "admin")
    if not await db.categorias.find_one({"_id": producto.categoria_id}):
        raise HTTPException(422, "Categoria inexistente")
    res = await db.productos.insert_one(producto.model_dump())
    doc = await db.productos.find_one({"_id": res.inserted_id})
    return doc_to_productoout(doc)


@app.put("/productos/{producto_id}", response_model=ProductoOut, tags=["mantenedor"])
async def actualizar_producto(
    producto_id: str,
    producto: ProductoIn,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "admin")
    if not await db.categorias.find_one({"_id": producto.categoria_id}):
        raise HTTPException(422, "Categoria inexistente")
    res = await db.productos.update_one(
        {"_id": object_id(producto_id)},
        {"$set": producto.model_dump()}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Producto no encontrado")
    doc = await db.productos.find_one({"_id": object_id(producto_id)})
    return doc_to_productoout(doc)


# Disponibilidad del producto (RF 7). Un producto con pedidos no se borra:
# se da de baja con activo = false.
@app.patch("/productos/{producto_id}/stock", response_model=ProductoOut, tags=["mantenedor"])
async def actualizar_stock(
    producto_id: str,
    datos: StockIn,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "admin")
    res = await db.productos.update_one(
        {"_id": object_id(producto_id)},
        {"$set": datos.model_dump()}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Producto no encontrado")
    doc = await db.productos.find_one({"_id": object_id(producto_id)})
    return doc_to_productoout(doc)


async def devolver_stock(descontados):
    for item in descontados:
        await db.productos.update_one({"_id": ObjectId(item["producto_id"])}, {"$inc": {"stock": item["cantidad"]}})


# Reserva de stock para un pedido. Solo la llama orders. Es idempotente por
# pedido_id: repetir la llamada no descuenta dos veces.
@app.post("/reservas", status_code=201, tags=["interno"])
async def reservar_stock(
    reserva: ReservaIn,
    origen=Depends(verificar_servicio("orders"))
):
    existente = await db.reservas.find_one({"_id": reserva.pedido_id})
    if existente:
        if existente["estado"] == "rechazada":
            raise HTTPException(409, "Stock insuficiente")
        return {"pedido_id": reserva.pedido_id, "estado": existente["estado"], "items": existente["items"]}

    # Se juntan las cantidades si el mismo producto viene dos veces
    cantidades = {}
    for item in reserva.items:
        object_id(item.producto_id)
        cantidades[item.producto_id] = cantidades.get(item.producto_id, 0) + item.cantidad

    try:
        await db.reservas.insert_one({"_id": reserva.pedido_id, "estado": "procesando", "items": []})
    except DuplicateKeyError:
        raise HTTPException(409, "La reserva ya se esta procesando")

    items = []
    for producto_id, cantidad in cantidades.items():
        doc = await db.productos.find_one_and_update(
            {"_id": ObjectId(producto_id), "activo": True, "stock": {"$gte": cantidad}},
            {"$inc": {"stock": -cantidad}}
        )
        if doc is None:
            # Se devuelve lo que ya se habia descontado
            await devolver_stock(items)
            await db.reservas.update_one({"_id": reserva.pedido_id}, {"$set": {"estado": "rechazada"}})
            raise HTTPException(409, "Stock insuficiente")
        # El precio lo fija inventory, no el navegador
        items.append({"producto_id": producto_id, "nombre": doc["nombre"], "precio": doc["precio"], "cantidad": cantidad})

    await db.reservas.update_one(
        {"_id": reserva.pedido_id},
        {"$set": {"estado": "reservada", "items": items}}
    )
    return {"pedido_id": reserva.pedido_id, "estado": "reservada", "items": items}


# Devuelve el stock de un pedido anulado. Idempotente: solo libera una vez.
@app.post("/reservas/{pedido_id}/liberar", tags=["interno"])
async def liberar_stock(
    pedido_id: str,
    origen=Depends(verificar_servicio("orders"))
):
    reserva = await db.reservas.find_one_and_update(
        {"_id": pedido_id, "estado": "reservada"},
        {"$set": {"estado": "liberada"}}
    )
    if reserva is None:
        existente = await db.reservas.find_one({"_id": pedido_id})
        if existente is None:
            raise HTTPException(404, "Reserva no encontrada")
        return {"pedido_id": pedido_id, "estado": existente["estado"]}
    await devolver_stock(reserva["items"])
    return {"pedido_id": pedido_id, "estado": "liberada"}
