import hashlib
import hmac
import html
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

# Adaptador de prueba de la plataforma de pago externa (como servipag o un
# webpay en modo prueba). No mueve dinero: conserva el contrato de una pasarela
# real: crear transaccion con API key, pagina de pago propia, aviso al comercio
# firmado con HMAC, reintento del aviso, consulta de estado y reembolso.
# Sus claves las configura el comercio en el "panel del proveedor"; aqui llegan
# por variables de entorno porque el proveedor no tiene acceso al Vault del comercio.

API_KEY = os.getenv("PROVEEDOR_API_KEY", "")
CLAVE_FIRMA = os.getenv("PROVEEDOR_CLAVE_FIRMA", "")
URL_PUBLICA = os.getenv("URL_PUBLICA", "http://localhost:9500")
URL_NOTIFICACION = os.getenv("URL_NOTIFICACION", "http://127.0.0.1:8000/api/pagos/notificacion")

if not API_KEY or not CLAVE_FIRMA:
    raise RuntimeError("PROVEEDOR_API_KEY y PROVEEDOR_CLAVE_FIRMA son obligatorias")

app = FastAPI(title="Proveedor de pago (adaptador de prueba)")

TRANSACCIONES = {}


def verificar_api_key(x_api_key: str):
    if not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="API key invalida")


def buscar(token):
    t = TRANSACCIONES.get(token)
    if t is None:
        raise HTTPException(404, "Transaccion no encontrada")
    return t


def firmar(cuerpo: bytes) -> str:
    return hmac.new(CLAVE_FIRMA.encode(), cuerpo, hashlib.sha256).hexdigest()


# Aviso al comercio. Cada aviso tiene su evento_id; un reintento reenvia el
# mismo evento (el comercio debe procesarlo una sola vez).
async def notificar(t, evento_id=None):
    evento = {
        "evento_id": evento_id or str(uuid.uuid4()),
        "token": t["token"],
        "referencia": t["referencia"],
        "estado": t["estado"],
        "monto": t["monto"],
        "fecha": datetime.now(timezone.utc).isoformat(),
    }
    t["ultimo_evento"] = evento["evento_id"]
    cuerpo = json.dumps(evento).encode()
    for _ in range(3):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(URL_NOTIFICACION, content=cuerpo,
                                      headers={"Content-Type": "application/json", "X-Firma": firmar(cuerpo)})
            if r.status_code == 200:
                return r.status_code
        except httpx.RequestError:
            pass
    return None


class TransaccionIn(BaseModel):
    referencia: str = Field(min_length=1, max_length=64)
    monto: int = Field(gt=0)
    url_retorno: str = Field(max_length=300)


@app.get("/health")
def health():
    return {"status": "OK", "service": "Proveedor de pago (prueba)"}


@app.post("/transacciones", status_code=201)
def crear_transaccion(datos: TransaccionIn, x_api_key: str = Header(default="")):
    verificar_api_key(x_api_key)
    token = secrets.token_urlsafe(16)
    TRANSACCIONES[token] = dict(datos.model_dump(), token=token, estado="pendiente")
    return {"token": token, "url_pago": f"{URL_PUBLICA}/pagar/{token}"}


@app.get("/transacciones/{token}")
def consultar(token: str, x_api_key: str = Header(default="")):
    verificar_api_key(x_api_key)
    t = buscar(token)
    return {"token": token, "referencia": t["referencia"], "estado": t["estado"], "monto": t["monto"]}


@app.post("/transacciones/{token}/reembolso")
def reembolsar(token: str, x_api_key: str = Header(default="")):
    verificar_api_key(x_api_key)
    t = buscar(token)
    if t["estado"] not in ("aprobado", "reembolsado"):
        raise HTTPException(409, "Solo se reembolsan pagos aprobados")
    t["estado"] = "reembolsado"
    return {"token": token, "estado": "reembolsado"}


# Solo laboratorio: reenvia el ultimo aviso para probar avisos duplicados
@app.post("/transacciones/{token}/reenviar-aviso")
async def reenviar_aviso(token: str, x_api_key: str = Header(default="")):
    verificar_api_key(x_api_key)
    t = buscar(token)
    return {"respuesta_comercio": await notificar(t, t.get("ultimo_evento"))}


# Pagina de pago del proveedor (la abre el navegador del cliente)
@app.get("/pagar/{token}", response_class=HTMLResponse)
def pagina_pago(token: str):
    t = buscar(token)
    if t["estado"] != "pendiente":
        return HTMLResponse(f"<p>Esta transacción ya fue {html.escape(t['estado'])}.</p>")
    monto = f"${t['monto']:,}".replace(",", ".")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Pasarela de pago de prueba</title>
<style>body{{font-family:sans-serif;max-width:380px;margin:3rem auto;padding:0 1rem}}
button{{width:100%;padding:.8rem;margin:.3rem 0;font-size:1rem;border:0;border-radius:.4rem;cursor:pointer}}
.ok{{background:#2e7d32;color:#fff}}.no{{background:#ddd}}</style></head><body>
<h1>Pasarela de pago</h1><p><small>Entorno de prueba: no se realizan cobros reales.</small></p>
<p>Comercio: <b>Aroma &amp; Café</b><br>Monto: <b>{monto}</b></p>
<form method="post"><button class="ok" name="accion" value="aprobar">Pagar con tarjeta de prueba</button>
<button class="no" name="accion" value="rechazar">Rechazar pago</button></form></body></html>"""


@app.post("/pagar/{token}")
async def procesar_pago(token: str, request: Request):
    t = buscar(token)
    accion = parse_qs((await request.body()).decode()).get("accion", [""])[0]
    if t["estado"] == "pendiente" and accion in ("aprobar", "rechazar"):
        t["estado"] = "aprobado" if accion == "aprobar" else "rechazado"
        await notificar(t)
    return RedirectResponse(t["url_retorno"], status_code=303)
