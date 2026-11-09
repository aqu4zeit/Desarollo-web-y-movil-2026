import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

# Adaptador de prueba de la API de mensajeria (proveedor externo).
# No envia correos reales: conserva el contrato (validar existencia del correo y
# enviar mensajes), exige credencial por cliente y deja los mensajes en un buzon
# de laboratorio para poder leer el codigo de verificacion y la boleta.

VAULT_ADDR = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")

LLAMADORES = ["clients", "payments", "laboratorio"]

# Correos que el proveedor de prueba informa como inexistentes
DOMINIOS_INEXISTENTES = ["noexiste.cl", "invalido.cl", "example.invalid"]

SECRETOS = {}
BUZON = []


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
        entrantes[origen] = (await leer_vault(f"tramos/{origen}-mensajeria"))["secret"]
    return entrantes


@asynccontextmanager
async def lifespan(app: FastAPI):
    global SECRETOS
    SECRETOS = await cargar_secretos()
    yield


app = FastAPI(
    title="API de mensajería (adaptador de prueba)",
    description="Valida correos y recibe mensajes salientes sin enviarlos",
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
            raise HTTPException(status_code=403, detail="Credencial de API invalida")
        return x_service_name
    return verificar


class ValidarIn(BaseModel):
    correo: str = Field(min_length=3, max_length=120)


class MensajeIn(BaseModel):
    para: str = Field(min_length=3, max_length=120)
    asunto: str = Field(min_length=1, max_length=150)
    cuerpo: str = Field(min_length=1, max_length=5000)


@app.get("/health", tags=["sistema"])
def health():
    return {"status": "OK", "service": "Mensajeria (prueba)"}


@app.post("/validar", tags=["correo"])
def validar_correo(datos: ValidarIn, origen=Depends(verificar_servicio("clients"))):
    dominio = datos.correo.split("@")[-1].lower()
    return {"correo": datos.correo, "existe": "@" in datos.correo and dominio not in DOMINIOS_INEXISTENTES}


@app.post("/enviar", status_code=202, tags=["correo"])
def enviar(mensaje: MensajeIn, origen=Depends(verificar_servicio("clients", "payments"))):
    BUZON.append({
        "para": mensaje.para.lower(),
        "asunto": mensaje.asunto,
        "cuerpo": mensaje.cuerpo,
        "origen": origen,
        "fecha": datetime.now(timezone.utc).isoformat()
    })
    return {"estado": "aceptado"}


# Solo para el laboratorio y las pruebas: lee lo que "llego" a un correo
@app.get("/buzon", tags=["laboratorio"])
def buzon(correo: str = Query(min_length=3), origen=Depends(verificar_servicio("laboratorio"))):
    return [m for m in BUZON if m["para"] == correo.lower()]
