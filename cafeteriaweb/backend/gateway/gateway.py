import logging
import os
import re
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

app = FastAPI(
    title="API Gateway Aroma & Café",
    description="Frontera de seguridad: sesión, autorización por ruta, enrutamiento y secretos de Vault"
)

security = HTTPBearer(auto_error=False)
log = logging.getLogger("gateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
# httpx registraria cada URL interna con sus parametros (pueden traer datos personales)
logging.getLogger("httpx").setLevel(logging.WARNING)

VAULT_ADDR = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false") == "true"
COOKIE_NAME = "session_token"

if not VAULT_TOKEN:
    raise RuntimeError("VAULT_TOKEN no está configurado")

# Direcciones internas de cada servicio (red privada)
SERVICIOS = {
    "auth": os.getenv("AUTH_SERVICE_URL", "http://127.0.0.1:8100"),
    "inventory": os.getenv("INVENTORY_URL", "http://127.0.0.1:9100"),
    "clients": os.getenv("CLIENTS_URL", "http://127.0.0.1:9000"),
    "orders": os.getenv("ORDERS_URL", "http://127.0.0.1:9200"),
    "payments": os.getenv("PAYMENTS_URL", "http://127.0.0.1:9300"),
    "despacho": os.getenv("DESPACHO_URL", "http://127.0.0.1:9400"),
    "graphql": os.getenv("GRAPHQL_URL", "http://127.0.0.1:8090"),
}

# Unicas cabeceras del navegador o del proveedor que pasan a los servicios
# (ademas de content-type): la firma del aviso de pago y la clave anti doble clic.
CABECERAS_PERMITIDAS = ["x-firma", "idempotency-key"]

PUBLICA = None      # sin sesion
SESION = []         # cualquier usuario con sesion valida


@dataclass
class Ruta:
    metodo: str
    publica: str
    servicio: str
    interna: str
    roles: Optional[List[str]]


# Lista explicita de rutas: lo que no esta aqui no se enruta.
RUTAS = [
    # Catalogo (inventory)
    Ruta("GET", "/api/categorias", "inventory", "/categorias", PUBLICA),
    Ruta("GET", "/api/productos", "inventory", "/productos", PUBLICA),
    Ruta("GET", "/api/productos/{id}", "inventory", "/productos/{id}", PUBLICA),
    Ruta("POST", "/api/productos", "inventory", "/productos", ["admin"]),
    Ruta("PUT", "/api/productos/{id}", "inventory", "/productos/{id}", ["admin"]),
    Ruta("PATCH", "/api/productos/{id}/stock", "inventory", "/productos/{id}/stock", ["admin"]),
    # Registro y perfil (clients)
    Ruta("POST", "/api/clientes/registro", "clients", "/clientes/registro", PUBLICA),
    Ruta("POST", "/api/clientes/verificar", "clients", "/clientes/verificar", PUBLICA),
    Ruta("POST", "/api/clientes/reenviar-codigo", "clients", "/clientes/reenviar-codigo", PUBLICA),
    Ruta("GET", "/api/clientes/me", "clients", "/clientes/me", ["cliente"]),
    Ruta("PUT", "/api/clientes/me", "clients", "/clientes/me", ["cliente"]),
    Ruta("PATCH", "/api/clientes/me/promociones", "clients", "/clientes/me/promociones", ["cliente"]),
    Ruta("GET", "/api/clientes", "clients", "/clientes", ["admin"]),
    Ruta("POST", "/api/clientes", "clients", "/clientes", ["admin"]),
    Ruta("GET", "/api/clientes/{id}", "clients", "/clientes/{id}", ["admin"]),
    Ruta("PUT", "/api/clientes/{id}", "clients", "/clientes/{id}", ["admin"]),
    Ruta("POST", "/api/contacto", "clients", "/contacto", PUBLICA),
    Ruta("GET", "/api/contacto", "clients", "/contacto", ["admin"]),
    # Mantenedor de usuarios y perfiles (Auth Service)
    Ruta("GET", "/api/usuarios", "auth", "/usuarios", ["admin"]),
    Ruta("POST", "/api/usuarios", "auth", "/usuarios", ["admin"]),
    Ruta("PUT", "/api/usuarios/{id}", "auth", "/usuarios/{id}", ["admin"]),
    # Pedidos (orders). Ver un pedido exige sesion; orders comprueba que sea propio.
    Ruta("POST", "/api/pedidos", "orders", "/pedidos", ["cliente"]),
    Ruta("GET", "/api/pedidos/mios", "orders", "/pedidos/mios", ["cliente"]),
    Ruta("GET", "/api/pedidos", "orders", "/pedidos", ["admin", "cajero", "despacho", "dueno"]),
    Ruta("GET", "/api/pedidos/{id}", "orders", "/pedidos/{id}", SESION),
    Ruta("POST", "/api/pedidos/{id}/anular", "orders", "/pedidos/{id}/anular", ["cliente", "admin"]),
    # Pagos, boletas y ventas (payments)
    Ruta("POST", "/api/pagos", "payments", "/pagos", ["cliente"]),
    Ruta("POST", "/api/pagos/notificacion", "payments", "/notificaciones", PUBLICA),
    Ruta("GET", "/api/pagos/{id}", "payments", "/pagos/{id}", SESION),
    Ruta("GET", "/api/boletas/pedido/{id}", "payments", "/boletas/pedido/{id}", ["cliente", "cajero", "admin", "dueno"]),
    Ruta("POST", "/api/boletas/{id}/reenviar", "payments", "/boletas/{id}/reenviar", ["cajero", "admin"]),
    Ruta("GET", "/api/ventas", "payments", "/ventas", ["cajero", "admin", "dueno"]),
    # Despacho (encargado de despacho)
    Ruta("GET", "/api/despacho/ordenes", "despacho", "/ordenes", ["despacho", "admin"]),
    Ruta("GET", "/api/despacho/ordenes/{id}", "despacho", "/ordenes/{id}", ["despacho", "admin"]),
    Ruta("PATCH", "/api/despacho/ordenes/{id}/estado", "despacho", "/ordenes/{id}/estado", ["despacho"]),
    Ruta("GET", "/api/despacho/ordenes/{id}/imprimir", "despacho", "/ordenes/{id}/imprimir", ["despacho", "admin"]),
    # GraphQL Gateway privado: exige sesion; cada consulta y campo se autoriza alla
    Ruta("POST", "/api/graphql", "graphql", "/graphql", SESION),
]

# Los parametros de ruta solo aceptan caracteres seguros (evita ../ y similares)
for ruta in RUTAS:
    ruta.patron = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[A-Za-z0-9_-]{1,64})", ruta.publica) + "$")


# Secretos de Vault. Se guardan 30 segundos en memoria para no consultar Vault
# en cada solicitud; una rotacion se aplica a mas tardar en ese plazo.
CACHE_SECRETOS = {"valores": None, "hasta": 0.0}
CACHE_SEGUNDOS = 30


async def get_gateway_secrets():
    if CACHE_SECRETOS["valores"] and time.monotonic() < CACHE_SECRETOS["hasta"]:
        return CACHE_SECRETOS["valores"]
    valores = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for servicio in SERVICIOS:
                response = await client.get(
                    f"{VAULT_ADDR}/v1/secret/data/tramos/gateway-{servicio}",
                    headers={"X-Vault-Token": VAULT_TOKEN}
                )
                if response.status_code != 200:
                    raise HTTPException(status_code=500, detail="No fue posible acceder a Vault")
                valores[servicio] = response.json()["data"]["data"]["secret"]
    except httpx.RequestError:
        raise HTTPException(status_code=500, detail="No fue posible acceder a Vault")
    CACHE_SECRETOS["valores"] = valores
    CACHE_SECRETOS["hasta"] = time.monotonic() + CACHE_SEGUNDOS
    return valores


# Limite de solicitudes por IP (ventana de 60 segundos). Se puede subir solo
# para la prueba de carga, que envia todo desde una misma IP.
LIMITES = {
    "general": int(os.getenv("LIMITE_POR_MINUTO", "120")),
    "login": int(os.getenv("LIMITE_LOGIN_POR_MINUTO", "10")),
}
VENTANAS = defaultdict(deque)


def limitar(ip: str, tipo: str):
    ahora = time.monotonic()
    ventana = VENTANAS[(ip, tipo)]
    while ventana and ahora - ventana[0] > 60:
        ventana.popleft()
    if len(ventana) >= LIMITES[tipo]:
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes, intente en un minuto",
                            headers={"Retry-After": "60"})
    ventana.append(ahora)


MAX_CUERPO = 64 * 1024


@app.middleware("http")
async def frontera(request: Request, call_next):
    inicio = time.monotonic()
    correlacion = request.headers.get("x-correlation-id", "")
    if not re.fullmatch(r"[0-9a-f-]{36}", correlacion):
        correlacion = str(uuid.uuid4())
    request.state.correlacion = correlacion
    request.state.usuario = "-"
    ip = request.client.host if request.client else "desconocida"
    try:
        limitar(ip, "general")
        if int(request.headers.get("content-length") or 0) > MAX_CUERPO:
            raise HTTPException(status_code=413, detail="Solicitud demasiado grande")
        response = await call_next(request)
    except HTTPException as e:
        response = JSONResponse({"detail": e.detail}, status_code=e.status_code, headers=e.headers)
    response.headers["X-Correlation-Id"] = correlacion
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    # El navegador no reutiliza respuestas con datos personales sin preguntar de nuevo
    response.headers["Cache-Control"] = "no-cache"
    # Registro sin tokens, claves ni cuerpos
    log.info("%s %s %s %s %dms user=%s", correlacion, request.method, request.url.path,
             response.status_code, (time.monotonic() - inicio) * 1000, request.state.usuario)
    return response


async def llamar_servicio(servicio, metodo, ruta, request: Request, json=None, content=None,
                          params=None, usuario=None):
    secretos = await get_gateway_secrets()
    # Se arma una cabecera nueva: nunca se reenvian X-Authenticated-* ni
    # X-Service-* que vengan del navegador.
    headers = {
        "X-Service-Name": "gateway",
        "X-Service-Secret": secretos[servicio],
        "X-Correlation-Id": request.state.correlacion,
    }
    if usuario:
        headers["X-Authenticated-User"] = usuario["user_id"]
        headers["X-Authenticated-Username"] = usuario["username"]
        headers["X-Authenticated-Roles"] = ",".join(usuario["roles"])
    content_type = request.headers.get("content-type")
    if content is not None and content_type:
        headers["content-type"] = content_type
    for nombre in CABECERAS_PERMITIDAS:
        if nombre in request.headers:
            headers[nombre] = request.headers[nombre][:200]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            return await client.request(metodo, f"{SERVICIOS[servicio]}{ruta}", json=json,
                                        content=content, params=params, headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"El servicio {servicio} no respondió a tiempo")
    except httpx.RequestError:
        if servicio == "auth":
            raise HTTPException(status_code=503, detail="Servicio de autenticación no disponible")
        raise HTTPException(status_code=502, detail="Backend no disponible")


def leer_token(request: Request, credentials: Optional[HTTPAuthorizationCredentials]):
    # El navegador usa la cookie HttpOnly; scripts y pruebas pueden usar Bearer
    token = request.cookies.get(COOKIE_NAME)
    if not token and credentials:
        token = credentials.credentials
    return token


async def introspeccion(request: Request, token: Optional[str]):
    if not token:
        return None
    response = await llamar_servicio("auth", "POST", "/introspect", request, json={"token": token})
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Servicio de autenticación no disponible")
    identity = response.json()
    if not identity.get("active", False):
        return None
    request.state.usuario = identity["user_id"]
    return identity


# Sesion del navegador (guia de autenticacion: /auth/login, /auth/me, /auth/logout)

class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=128)


@app.get("/health", tags=["sistema"])
def health():
    return {"status": "OK", "service": "API Gateway"}


@app.post("/auth/login", tags=["sesion"])
async def login(datos: LoginRequest, request: Request, response: Response):
    limitar(request.client.host if request.client else "desconocida", "login")
    upstream = await llamar_servicio("auth", "POST", "/login", request, json=datos.model_dump())
    if upstream.status_code != 200:
        return Response(content=upstream.content, status_code=upstream.status_code,
                        media_type="application/json")
    token = upstream.json()["access_token"]
    identity = await introspeccion(request, token)
    response.set_cookie(
        COOKIE_NAME, token, max_age=upstream.json()["expires_in"],
        httponly=True, samesite="strict", secure=COOKIE_SECURE, path="/"
    )
    return {"message": "Sesión iniciada", "usuario": {"username": identity["username"], "roles": identity["roles"]}}


@app.get("/auth/me", tags=["sesion"])
async def me(request: Request, credentials=Depends(security)):
    identity = await introspeccion(request, leer_token(request, credentials))
    if identity is None:
        raise HTTPException(status_code=401, detail="No existe sesión válida")
    return {
        "user_id": identity["user_id"],
        "username": identity["username"],
        "roles": identity["roles"],
        "expires_at": identity["expires_at"]
    }


@app.post("/auth/logout", tags=["sesion"])
async def logout(request: Request, response: Response, credentials=Depends(security)):
    token = leer_token(request, credentials)
    if token:
        # Logout = revocacion en el Auth Service + eliminacion de la cookie
        await llamar_servicio("auth", "POST", "/logout", request, json={"token": token})
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict", secure=COOKIE_SECURE)
    return {"message": "Sesión finalizada"}


# Enrutamiento de la API segun la tabla RUTAS

def buscar_ruta(metodo: str, path: str):
    existe_path = False
    for ruta in RUTAS:
        coincidencia = ruta.patron.match(path)
        if coincidencia:
            existe_path = True
            if ruta.metodo == metodo:
                return ruta, coincidencia.groupdict()
    if existe_path:
        raise HTTPException(status_code=405, detail="Método no permitido")
    raise HTTPException(status_code=404, detail="Ruta no encontrada")


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH"])
async def proxy(path: str, request: Request, credentials=Depends(security)):
    ruta, parametros = buscar_ruta(request.method, request.url.path)
    token = leer_token(request, credentials)

    if ruta.roles is PUBLICA:
        # Ruta publica: si hay sesion se propaga la identidad, si no, se atiende igual
        usuario = await introspeccion(request, token) if token else None
    else:
        usuario = await introspeccion(request, token)
        if usuario is None:
            raise HTTPException(status_code=401, detail="No existe sesión válida, token inválido o expirado")
        if ruta.roles and not any(rol in usuario["roles"] for rol in ruta.roles):
            raise HTTPException(status_code=403, detail="El usuario no tiene permisos para esta operación")

    interna = ruta.interna.format(**parametros)
    body = await request.body()
    upstream = await llamar_servicio(ruta.servicio, request.method, interna, request,
                                     content=body, params=request.query_params, usuario=usuario)

    response_headers = {}
    if "content-type" in upstream.headers:
        response_headers["content-type"] = upstream.headers["content-type"]
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)
