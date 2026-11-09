import hashlib
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import List, Literal, Optional

import httpx
from bson import ObjectId
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, field_validator

# Configuracion
DB_NAME = os.getenv("DB_NAME", "aroma_clients")
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://127.0.0.1:8100")
MENSAJERIA_URL = os.getenv("MENSAJERIA_URL", "http://127.0.0.1:9600")

# Quienes pueden llamar a clients
LLAMADORES = ["gateway", "graphql", "orders", "payments"]
# A quienes llama clients
DESTINOS = ["auth", "mensajeria"]

CODIGO_MINUTOS = 15
CODIGO_INTENTOS = 5

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
        entrantes[origen] = (await leer_vault(f"tramos/{origen}-clients"))["secret"]
    salientes = {}
    for destino in DESTINOS:
        salientes[destino] = (await leer_vault(f"tramos/clients-{destino}"))["secret"]
    propios = await leer_vault("servicios/clients")
    return {"mongodb_uri": propios["mongodb_uri"], "entrantes": entrantes, "salientes": salientes}


# Perfil de la clienta de prueba (su credencial USR-0005 la crea el Auth Service)
CLIENTES_INICIALES = [
    {
        "user_id": "USR-0005", "run": "11111111-1", "nombre": "Camila Rojas Soto",
        "direccion": "San Diego 850", "comuna": "Santiago", "provincia": "Santiago",
        "region": "Metropolitana", "fecha_nacimiento": "1998-04-12", "sexo": "femenino",
        "correo": "camila@aroma.cl", "telefono": "+56911111111", "promociones": True,
        "verificado": True
    }
]


async def cargar_datos_iniciales():
    await db.clientes.create_index("correo", unique=True)
    await db.clientes.create_index("run", unique=True)
    await db.clientes.create_index("user_id", unique=True, sparse=True)
    if await db.clientes.count_documents({}) == 0:
        await db.clientes.insert_many([dict(c) for c in CLIENTES_INICIALES])


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db, SECRETOS, SALIENTES
    config = await cargar_secretos()
    SECRETOS = config["entrantes"]
    SALIENTES = config["salientes"]
    client = AsyncIOMotorClient(config["mongodb_uri"], tz_aware=True)
    db = client[DB_NAME]
    await cargar_datos_iniciales()
    yield
    client.close()


app = FastAPI(
    title="Clients Service",
    description="Registro y perfil de clientes, promociones y contacto de Aroma & Café",
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


# Llamada a otro servicio con la credencial del tramo clients-<destino>
async def llamar(destino, url, metodo, ruta, json=None):
    try:
        async with httpx.AsyncClient(timeout=5.0) as cliente_http:
            return await cliente_http.request(
                metodo, f"{url}{ruta}", json=json,
                headers={"X-Service-Name": "clients", "X-Service-Secret": SALIENTES[destino]}
            )
    except httpx.RequestError:
        raise HTTPException(503, f"Servicio {destino} no disponible")


# Validaciones
def run_valido(run: str) -> bool:
    # RUN chileno con digito verificador (modulo 11)
    if not re.fullmatch(r"\d{7,8}-[\dkK]", run):
        return False
    cuerpo, dv = run.split("-")
    suma, multiplo = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplo
        multiplo = 2 if multiplo == 7 else multiplo + 1
    resto = 11 - suma % 11
    esperado = "0" if resto == 11 else "K" if resto == 10 else str(resto)
    return dv.upper() == esperado


CORREO_REGEX = r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}"


# Modelos
class DatosContacto(BaseModel):
    nombre: str = Field(min_length=3, max_length=100)
    direccion: str = Field(min_length=3, max_length=150)
    comuna: str = Field(min_length=2, max_length=60)
    provincia: str = Field(min_length=2, max_length=60)
    region: str = Field(min_length=2, max_length=60)
    telefono: str = Field(pattern=r"^\+569\d{8}$", description="Formato +569XXXXXXXX")


class ClienteRegistro(DatosContacto):
    run: str
    fecha_nacimiento: date
    sexo: Literal["femenino", "masculino", "otro", "prefiero_no_decir"]
    correo: str = Field(max_length=120, pattern=CORREO_REGEX)
    password: str = Field(min_length=8, max_length=128)
    promociones: bool = False

    @field_validator("run")
    @classmethod
    def validar_run(cls, valor):
        if not run_valido(valor):
            raise ValueError("RUN no válido.")
        return valor.upper()

    @field_validator("fecha_nacimiento")
    @classmethod
    def validar_fecha(cls, valor):
        hoy = date.today()
        if valor >= hoy or valor.year < hoy.year - 120:
            raise ValueError("Fecha no válida.")
        return valor


class ClienteOut(DatosContacto):
    id: str
    user_id: Optional[str]
    run: str
    fecha_nacimiento: date
    sexo: str
    correo: str
    promociones: bool
    verificado: bool


# Lo minimo que necesitan orders, payments y graphql (despacho y boleta)
class ClienteResumen(BaseModel):
    id: str
    user_id: str
    nombre: str
    correo: str
    direccion: str
    comuna: str
    telefono: str


class VerificarIn(BaseModel):
    correo: str = Field(max_length=120)
    codigo: str = Field(pattern=r"^\d{6}$")


class CorreoIn(BaseModel):
    correo: str = Field(max_length=120, pattern=CORREO_REGEX)


class PromocionesIn(BaseModel):
    promociones: bool


class ContactoIn(BaseModel):
    nombre: str = Field(min_length=3, max_length=100)
    correo: str = Field(max_length=120, pattern=CORREO_REGEX)
    mensaje: str = Field(min_length=5, max_length=1000)


def doc_to_clienteout(doc) -> ClienteOut:
    return ClienteOut(
        id=str(doc["_id"]),
        user_id=doc.get("user_id"),
        run=doc["run"],
        nombre=doc["nombre"],
        direccion=doc["direccion"],
        comuna=doc["comuna"],
        provincia=doc["provincia"],
        region=doc["region"],
        fecha_nacimiento=doc["fecha_nacimiento"],
        sexo=doc["sexo"],
        correo=doc["correo"],
        telefono=doc["telefono"],
        promociones=doc.get("promociones", False),
        verificado=doc.get("verificado", False),
    )


def doc_to_resumen(doc) -> ClienteResumen:
    return ClienteResumen(
        id=str(doc["_id"]), user_id=doc["user_id"], nombre=doc["nombre"], correo=doc["correo"],
        direccion=doc["direccion"], comuna=doc["comuna"], telefono=doc["telefono"]
    )


def hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.encode()).hexdigest()


async def enviar_codigo(correo: str):
    codigo = f"{secrets.randbelow(10**6):06d}"
    await db.clientes.update_one(
        {"correo": correo},
        {"$set": {
            "codigo_hash": hash_codigo(codigo),
            "codigo_expira": datetime.now(timezone.utc) + timedelta(minutes=CODIGO_MINUTOS),
            "codigo_intentos": 0
        }}
    )
    r = await llamar("mensajeria", MENSAJERIA_URL, "POST", "/enviar", {
        "para": correo,
        "asunto": "Aroma & Café: verifica tu correo",
        "cuerpo": f"Tu código de verificación es {codigo}. Vence en {CODIGO_MINUTOS} minutos."
    })
    if r.status_code != 202:
        raise HTTPException(502, "No fue posible enviar el código de verificación")


# Registro usado por la web (RF 5) y por el administrador en el local (RF 6)
async def registrar(datos: ClienteRegistro):
    correo = datos.correo.lower()
    if await db.clientes.find_one({"$or": [{"correo": correo}, {"run": datos.run}]}):
        raise HTTPException(409, "Ya existe una cuenta con ese correo o RUN.")

    r = await llamar("mensajeria", MENSAJERIA_URL, "POST", "/validar", {"correo": correo})
    if r.status_code != 200:
        raise HTTPException(502, "No fue posible validar el correo")
    if not r.json()["existe"]:
        raise HTTPException(422, "Correo no válido.")

    # La clave no se guarda en clients: se entrega al Auth Service, que guarda su hash
    r = await llamar("auth", AUTH_SERVICE_URL, "POST", "/usuarios", {
        "username": correo, "password": datos.password, "roles": ["cliente"], "activo": False
    })
    if r.status_code == 409:
        raise HTTPException(409, "Ya existe una cuenta con ese correo o RUN.")
    if r.status_code != 201:
        raise HTTPException(502, "No fue posible crear la credencial")

    perfil = datos.model_dump(exclude={"password"})
    perfil.update({
        "correo": correo,
        "fecha_nacimiento": datos.fecha_nacimiento.isoformat(),
        "user_id": r.json()["id"],
        "verificado": False
    })
    res = await db.clientes.insert_one(perfil)
    await enviar_codigo(correo)
    return {"id": str(res.inserted_id), "message": "Cliente registrado. Revise su correo para verificar la cuenta."}


# EndPoints

@app.get("/health", tags=["sistema"])
def health():
    return {"status": "OK", "service": "Clients Service"}


@app.post("/clientes/registro", status_code=201, tags=["registro"])
async def registro_web(datos: ClienteRegistro, origen=Depends(verificar_servicio("gateway"))):
    return await registrar(datos)


@app.post("/clientes/verificar", tags=["registro"])
async def verificar_correo(datos: VerificarIn, origen=Depends(verificar_servicio("gateway"))):
    doc = await db.clientes.find_one({"correo": datos.correo.lower(), "verificado": False})
    error = HTTPException(400, "Código inválido o vencido")
    if not doc or "codigo_hash" not in doc:
        raise error
    if doc["codigo_intentos"] >= CODIGO_INTENTOS or datetime.now(timezone.utc) > doc["codigo_expira"]:
        raise error
    if not secrets.compare_digest(hash_codigo(datos.codigo), doc["codigo_hash"]):
        await db.clientes.update_one({"_id": doc["_id"]}, {"$inc": {"codigo_intentos": 1}})
        raise error

    r = await llamar("auth", AUTH_SERVICE_URL, "POST", f"/usuarios/{doc['user_id']}/activar")
    if r.status_code != 200:
        raise HTTPException(502, "No fue posible activar la cuenta")
    await db.clientes.update_one(
        {"_id": doc["_id"]},
        {"$set": {"verificado": True}, "$unset": {"codigo_hash": "", "codigo_expira": "", "codigo_intentos": ""}}
    )
    return {"message": "Correo verificado. Ya puede ingresar."}


@app.post("/clientes/reenviar-codigo", tags=["registro"])
async def reenviar_codigo(datos: CorreoIn, origen=Depends(verificar_servicio("gateway"))):
    # Misma respuesta exista o no el correo, para no revelar quien esta registrado
    if await db.clientes.find_one({"correo": datos.correo.lower(), "verificado": False}):
        await enviar_codigo(datos.correo.lower())
    return {"message": "Si el correo está pendiente de verificación, se envió un nuevo código."}


@app.get("/clientes/me", response_model=ClienteOut, tags=["perfil"])
async def mi_perfil(origen=Depends(verificar_servicio("gateway")), usuario=Depends(identidad)):
    exigir_rol(usuario, "cliente")
    doc = await db.clientes.find_one({"user_id": usuario["user_id"]})
    if not doc:
        raise HTTPException(404, "Perfil no encontrado")
    return doc_to_clienteout(doc)


# El cliente puede cambiar sus datos de contacto y despacho; RUN y correo no
@app.put("/clientes/me", response_model=ClienteOut, tags=["perfil"])
async def actualizar_mi_perfil(
    datos: DatosContacto,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "cliente")
    res = await db.clientes.update_one({"user_id": usuario["user_id"]}, {"$set": datos.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(404, "Perfil no encontrado")
    return doc_to_clienteout(await db.clientes.find_one({"user_id": usuario["user_id"]}))


# Promociones y ofertas solo para clientes registrados (RF 5)
@app.patch("/clientes/me/promociones", response_model=ClienteOut, tags=["perfil"])
async def suscribir_promociones(
    datos: PromocionesIn,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "cliente")
    res = await db.clientes.update_one({"user_id": usuario["user_id"]}, {"$set": datos.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(404, "Perfil no encontrado")
    return doc_to_clienteout(await db.clientes.find_one({"user_id": usuario["user_id"]}))


# Mantenedor de clientes (RF 6 y 10), solo administrador
@app.get("/clientes", response_model=List[ClienteOut], tags=["mantenedor"])
async def listar_clientes(
    q: Optional[str] = Query(None, max_length=50, description="Filtro por nombre, correo o RUN"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "admin")
    query = {}
    if q:
        patron = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"nombre": patron}, {"correo": patron}, {"run": patron}]
    clientes = []
    async for doc in db.clientes.find(query).sort("nombre", 1).skip(skip).limit(limit):
        clientes.append(doc_to_clienteout(doc))
    return clientes


@app.post("/clientes", status_code=201, tags=["mantenedor"])
async def registro_en_local(
    datos: ClienteRegistro,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "admin")
    return await registrar(datos)


@app.get("/clientes/{cliente_id}", response_model=ClienteOut, tags=["mantenedor"])
async def obtener_cliente(
    cliente_id: str,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "admin")
    if not ObjectId.is_valid(cliente_id):
        raise HTTPException(400, "id invalido")
    doc = await db.clientes.find_one({"_id": ObjectId(cliente_id)})
    if not doc:
        raise HTTPException(404, "Cliente no encontrado")
    return doc_to_clienteout(doc)


@app.put("/clientes/{cliente_id}", response_model=ClienteOut, tags=["mantenedor"])
async def actualizar_cliente(
    cliente_id: str,
    datos: DatosContacto,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "admin")
    if not ObjectId.is_valid(cliente_id):
        raise HTTPException(400, "id invalido")
    res = await db.clientes.update_one({"_id": ObjectId(cliente_id)}, {"$set": datos.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(404, "Cliente no encontrado")
    return doc_to_clienteout(await db.clientes.find_one({"_id": ObjectId(cliente_id)}))


# Datos minimos de un cliente para despacho y boleta (uso interno)
@app.get("/interno/clientes/{user_id}", response_model=ClienteResumen, tags=["interno"])
async def resumen_cliente(user_id: str, origen=Depends(verificar_servicio("orders", "payments", "graphql"))):
    doc = await db.clientes.find_one({"user_id": user_id, "verificado": True})
    if not doc:
        raise HTTPException(404, "Cliente no encontrado")
    return doc_to_resumen(doc)


# Formulario de contacto de la web (publico)
@app.post("/contacto", status_code=201, tags=["contacto"])
async def enviar_contacto(datos: ContactoIn, origen=Depends(verificar_servicio("gateway"))):
    await db.contacto.insert_one(dict(datos.model_dump(), fecha=datetime.now(timezone.utc), leido=False))
    return {"message": "Mensaje recibido. Te responderemos pronto."}


@app.get("/contacto", tags=["contacto"])
async def listar_contacto(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "admin")
    mensajes = []
    async for doc in db.contacto.find().sort("fecha", -1).skip(skip).limit(limit):
        mensajes.append({
            "id": str(doc["_id"]), "nombre": doc["nombre"], "correo": doc["correo"],
            "mensaje": doc["mensaje"], "fecha": doc["fecha"].isoformat(), "leido": doc["leido"]
        })
    return mensajes
