import os
import secrets

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

app = FastAPI(title = "Local API Gateway")

# Datos de conexion al secret manager (Vault)
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")

if not VAULT_TOKEN:
    raise RuntimeError("VAULT_TOKEN no esta configurado")

BACKEND_URL = "http://localhost:9000" # fastapi - clientes
BACKEND_URL2 = "http://localhost:9100" # fastapi2 - productos

bearer = HTTPBearer(auto_error = False)

# Funcion para obtener los secretos desde Vault
async def get_vault_secrets():
    url = f"{VAULT_ADDR}/v1/secret/data/gateway"
    headers = {"X-Vault-Token": VAULT_TOKEN}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers = headers)

    if response.status_code != 200:
        raise HTTPException(status_code = 500, detail = "No se pudo acceder a Vault")

    vault_response = response.json()
    return vault_response["data"]["data"]

# Autenticacion del cliente con Bearer token
async def authenticate_client(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials:
        raise HTTPException(status_code = 401, detail = "Bearer token requerido")

    vault_secrets = await get_vault_secrets()
    expected_token = vault_secrets["client_token"]

    if not secrets.compare_digest(credentials.credentials, expected_token):
        raise HTTPException(status_code = 401, detail = "Token invalido")

    return {
        "client_id": "student-client",
        "backend_secret": vault_secrets["backend_shared_secret"]
    }

# http://localhost:8000/api/clientes -> http://localhost:9000/clientes
# http://localhost:8000/api/productos -> http://localhost:9100/productos
@app.api_route("/api/{path:path}", methods = ["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request, auth = Depends(authenticate_client)):
    if path.startswith("productos"):
        target_url = f"{BACKEND_URL2}/{path}"
    else:
        target_url = f"{BACKEND_URL}/{path}"

    body = await request.body()

    gateway_headers = {
        "X-Gateway-Secret": auth["backend_secret"],
        "X-Authenticated-Client": auth["client_id"]
    }

    content_type = request.headers.get("content-type")
    if content_type:
        gateway_headers["Content-Type"] = content_type

    try:
        async with httpx.AsyncClient(timeout = 10) as client:
            upstream = await client.request(
                method = request.method,
                url = target_url,
                params = request.query_params,
                content = body,
                headers = gateway_headers
            )
    except httpx.RequestError:
        raise HTTPException(status_code = 502, detail = "Backend no disponible")

    response_headers = {}
    if "content-type" in upstream.headers:
        response_headers["content-type"] = upstream.headers["content-type"]

    return Response(
        content = upstream.content,
        status_code = upstream.status_code,
        headers = response_headers
    )
