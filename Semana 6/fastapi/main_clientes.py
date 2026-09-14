from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from contextlib import asynccontextmanager

#Configuration BD mongodb
MONGODB_URI = "mongodb://localhost:27017"
DB_NAME = "UNAB"
COLL_NAME = "clientes"

client: AsyncIOMotorClient | None = None
db = None
coll = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db, coll
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DB_NAME]
    coll = db[COLL_NAME]
    yield
    client.close()

app = FastAPI(title="FastAPI 8481", version="1.0.0", lifespan=lifespan)

class ClienteIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nombre: str = Field(min_length=1, description="Nombre del cliente")
    password: str = Field(min_length=1, alias="pass", description="Contraseña")

class ClienteOut(ClienteIn):
    id: str

def doc_to_clienteout(doc) -> ClienteOut:
    return ClienteOut(
        id=str(doc["_id"]),
        nombre=doc["nombre"],
        password=doc.get("pass", ""),
    )

#EndPoints

@app.get("/health", tags=["sistema"])
def health():
    return {"status": "ok"}

@app.get("/clientes", response_model=List[ClienteOut])
async def listar_clientes(
    q: Optional[str] = Query(None, description="Filtro por nombre que contenga q"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    query = {}
    if q:
        query["nombre"] = {"$regex": q, "$options": "i"}
    cursor = coll.find(query).skip(skip).limit(limit)
    clientes: List[ClienteOut] = []
    async for doc in cursor:
        clientes.append(doc_to_clienteout(doc))
    return clientes

@app.post("/clientes", response_model=ClienteOut, status_code=201, tags=["clientes"])
async def crear_cliente(cliente: ClienteIn):
    res = await coll.insert_one(cliente.model_dump(by_alias=True))
    doc = await coll.find_one({"_id": res.inserted_id})
    return doc_to_clienteout(doc)

# http://localhost:8098/clientes/2
@app.get("/clientes/{cliente_id}", response_model=ClienteOut)
async def obtener_cliente(cliente_id: str):
    if not ObjectId.is_valid(cliente_id):
        raise HTTPException(400, "id invalido")
    doc = await coll.find_one({"_id": ObjectId(cliente_id)})
    if not doc:
        raise HTTPException(404, "Cliente no encontrado")
    return doc_to_clienteout(doc)

@app.put("/clientes/{cliente_id}", response_model=ClienteOut)
async def actualizar_cliente(cliente_id: str, cliente: ClienteIn):
    if not ObjectId.is_valid(cliente_id):
        raise HTTPException(400, "id invalido")
    res = await coll.update_one(
        {"_id": ObjectId(cliente_id)},
        {"$set": cliente.model_dump(by_alias=True)}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Cliente no encontrado")
    doc = await coll.find_one({"_id": ObjectId(cliente_id)})
    return doc_to_clienteout(doc)

@app.delete("/clientes/{cliente_id}", status_code=204, tags=["clientes"])
async def eliminar_cliente(cliente_id: str):
    if not ObjectId.is_valid(cliente_id):
        raise HTTPException(400, "id invalido")
    res = await coll.delete_one({"_id": ObjectId(cliente_id)})
    if res.deleted_count == 0:
        raise HTTPException(404, "Cliente no encontrado")
    return None
