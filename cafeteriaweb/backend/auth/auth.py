import hashlib
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, FastAPI, Header, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

# Configuracion
DB_NAME = os.getenv("DB_NAME", "aroma_auth")
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")

TOKEN_LIFETIME_MINUTES = 15

# Servicios que pueden llamar al Auth Service (secret/tramos/<origen>-auth)
LLAMADORES = ["gateway", "clients"]

ROLES_VALIDOS = ["cliente", "cajero", "despacho", "admin", "dueno"]

# Hash adaptativo con sal (Argon2id), como recomienda la guia de autenticacion
hasher = PasswordHasher()

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


async def cargar_secretos():
    entrantes = {}
    for origen in LLAMADORES:
        entrantes[origen] = (await leer_vault(f"tramos/{origen}-auth"))["secret"]
    propios = await leer_vault("servicios/auth")
    return {"entrantes": entrantes, **propios}


# Usuarios internos de prueba. Las claves no estan en el codigo: se leen de Vault.
USUARIOS_INICIALES = [
    {"_id": "USR-0001", "username": "admin@aroma.cl", "roles": ["admin"], "clave": "clave_admin"},
    {"_id": "USR-0002", "username": "dueno@aroma.cl", "roles": ["dueno"], "clave": "clave_dueno"},
    {"_id": "USR-0003", "username": "cajero@aroma.cl", "roles": ["cajero"], "clave": "clave_cajero"},
    {"_id": "USR-0004", "username": "despacho@aroma.cl", "roles": ["despacho"], "clave": "clave_despacho"},
    {"_id": "USR-0005", "username": "camila@aroma.cl", "roles": ["cliente"], "clave": "clave_cliente"},
]


async def cargar_datos_iniciales(config):
    await db.usuarios.create_index("username", unique=True)
    # Las sesiones vencidas las borra MongoDB solo (indice TTL)
    await db.sesiones.create_index("expires_at", expireAfterSeconds=0)
    if await db.usuarios.count_documents({}) == 0:
        await db.usuarios.insert_many([
            {
                "_id": u["_id"],
                "username": u["username"],
                "password_hash": hasher.hash(config[u["clave"]]),
                "roles": u["roles"],
                "activo": True
            }
            for u in USUARIOS_INICIALES
        ])


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db, SECRETOS
    config = await cargar_secretos()
    SECRETOS = config["entrantes"]
    client = AsyncIOMotorClient(config["mongodb_uri"], tz_aware=True)
    db = client[DB_NAME]
    await cargar_datos_iniciales(config)
    yield
    client.close()


app = FastAPI(
    title="Authentication Service",
    description="Credenciales, sesiones e introspección de tokens de Aroma & Café",
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


# En la base se guarda el hash del token, no el token
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# Modelos
class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=128)


class IntrospectionRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class UsuarioIn(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    roles: List[str] = Field(min_length=1)
    activo: bool = True


class UsuarioUpdate(BaseModel):
    roles: List[str] = Field(min_length=1)
    activo: bool


class UsuarioOut(BaseModel):
    id: str
    username: str
    roles: List[str]
    activo: bool


def doc_to_usuarioout(doc) -> UsuarioOut:
    return UsuarioOut(id=doc["_id"], username=doc["username"], roles=doc["roles"], activo=doc["activo"])


def validar_roles(roles):
    for rol in roles:
        if rol not in ROLES_VALIDOS:
            raise HTTPException(422, f"Rol invalido: {rol}")


# EndPoints

@app.get("/health", tags=["sistema"])
def health():
    return {"status": "OK", "service": "Authentication service"}


@app.post("/login", tags=["sesion"])
async def login(request: LoginRequest, origen=Depends(verificar_servicio("gateway"))):
    user = await db.usuarios.find_one({"username": request.username.lower()})
    # Mismo mensaje si el usuario no existe o la clave es incorrecta
    if user is None:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    try:
        hasher.verify(user["password_hash"], request.password)
    except VerifyMismatchError:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    # Un cliente sin verificar su correo o una cuenta dada de baja no ingresa
    if not user["activo"]:
        raise HTTPException(status_code=403, detail="Cuenta no verificada o desactivada.")

    access_token = secrets.token_urlsafe(32)
    expiration = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_LIFETIME_MINUTES)
    await db.sesiones.insert_one({
        "_id": hash_token(access_token),
        "user_id": user["_id"],
        "username": user["username"],
        "roles": user["roles"],
        "expires_at": expiration
    })
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": TOKEN_LIFETIME_MINUTES * 60
    }


@app.post("/introspect", tags=["sesion"])
async def introspect(request: IntrospectionRequest, origen=Depends(verificar_servicio("gateway"))):
    session = await db.sesiones.find_one({"_id": hash_token(request.token)})
    if session is None:
        return {"active": False}
    if datetime.now(timezone.utc) > session["expires_at"]:
        await db.sesiones.delete_one({"_id": session["_id"]})
        return {"active": False}
    return {
        "active": True,
        "user_id": session["user_id"],
        "username": session["username"],
        "roles": session["roles"],
        "expires_at": session["expires_at"].isoformat()
    }


@app.post("/logout", tags=["sesion"])
async def logout(request: IntrospectionRequest, origen=Depends(verificar_servicio("gateway"))):
    await db.sesiones.delete_one({"_id": hash_token(request.token)})
    return {"message": "Sesión finalizada"}


# Mantenedor de usuarios (RF 10). El administrador asigna los perfiles (RF 12).
@app.get("/usuarios", response_model=List[UsuarioOut], tags=["usuarios"])
async def listar_usuarios(origen=Depends(verificar_servicio("gateway")), usuario=Depends(identidad)):
    exigir_rol(usuario, "admin")
    usuarios = []
    async for doc in db.usuarios.find().sort("_id", 1):
        usuarios.append(doc_to_usuarioout(doc))
    return usuarios


# Crea una credencial. El gateway la usa para el administrador; clients la usa
# en el registro web y solo puede crear clientes inactivos hasta verificar el correo.
@app.post("/usuarios", response_model=UsuarioOut, status_code=201, tags=["usuarios"])
async def crear_usuario(
    datos: UsuarioIn,
    origen=Depends(verificar_servicio("gateway", "clients")),
    usuario=Depends(identidad)
):
    validar_roles(datos.roles)
    if origen == "gateway":
        exigir_rol(usuario, "admin")
    elif datos.roles != ["cliente"] or datos.activo:
        raise HTTPException(403, "clients solo crea clientes pendientes de verificacion")
    nuevo = {
        "_id": "USR-" + secrets.token_hex(4).upper(),
        "username": datos.username.lower(),
        "password_hash": hasher.hash(datos.password),
        "roles": datos.roles,
        "activo": datos.activo
    }
    try:
        await db.usuarios.insert_one(nuevo)
    except DuplicateKeyError:
        raise HTTPException(409, "El usuario ya existe")
    return doc_to_usuarioout(nuevo)


@app.put("/usuarios/{user_id}", response_model=UsuarioOut, tags=["usuarios"])
async def actualizar_usuario(
    user_id: str,
    datos: UsuarioUpdate,
    origen=Depends(verificar_servicio("gateway")),
    usuario=Depends(identidad)
):
    exigir_rol(usuario, "admin")
    validar_roles(datos.roles)
    if user_id == usuario["user_id"] and ("admin" not in datos.roles or not datos.activo):
        raise HTTPException(409, "El administrador no puede quitarse su propio acceso")
    res = await db.usuarios.update_one({"_id": user_id}, {"$set": datos.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(404, "Usuario no encontrado")
    # Un cambio de perfil o una baja cierra las sesiones abiertas de ese usuario
    await db.sesiones.delete_many({"user_id": user_id})
    return doc_to_usuarioout(await db.usuarios.find_one({"_id": user_id}))


# clients activa la cuenta cuando el cliente confirma su correo
@app.post("/usuarios/{user_id}/activar", response_model=UsuarioOut, tags=["usuarios"])
async def activar_usuario(user_id: str, origen=Depends(verificar_servicio("clients"))):
    res = await db.usuarios.update_one({"_id": user_id, "roles": ["cliente"]},
                                       {"$set": {"activo": True}})
    if res.matched_count == 0:
        raise HTTPException(404, "Usuario no encontrado")
    return doc_to_usuarioout(await db.usuarios.find_one({"_id": user_id}))
