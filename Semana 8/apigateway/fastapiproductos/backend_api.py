import os
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException

# Secreto interno compartido con el gateway
INTERNAL_GATEWAY_SECRET = os.getenv("INTERNAL_GATEWAY_SECRET")

if not INTERNAL_GATEWAY_SECRET:
    raise RuntimeError("INTERNAL_GATEWAY_SECRET no esta configurado")

app = FastAPI(
    title = "API de productos",
    description = "API ubicada en el localhost enrutada por el API gateway /api/productos"
)

# Valida que la solicitud venga desde el gateway
def verify_gateway(x_gateway_secret: str = Header(default = "")):
    if not secrets.compare_digest(x_gateway_secret, INTERNAL_GATEWAY_SECRET):
        raise HTTPException(status_code = 403, detail = "Solicitud no autorizada desde gateway")

@app.get("/health")
def salud():
    return {
        "estado": "OK",
        "servicio": "API de Productos"
    }

@app.get("/productos")
def productos(
    gateway = Depends(verify_gateway),
    x_authenticated_client: str = Header(default = None)
):
    return {
        "cliente_autenticado": x_authenticated_client,
        "productos": [
            {"id": 1, "nombre": "Cafe Americano", "precio": 4000},
            {"id": 2, "nombre": "Cafe Latte", "precio": 5500},
            {"id": 3, "nombre": "Cappuccino", "precio": 5500},
            {"id": 4, "nombre": "Mocachino", "precio": 6000},
            {"id": 5, "nombre": "Te Chai", "precio": 5000},
            {"id": 6, "nombre": "Chocolate Caliente", "precio": 5500},
            {"id": 7, "nombre": "Croissant", "precio": 4500},
            {"id": 8, "nombre": "Muffin de Arandanos", "precio": 5000}
        ]
    }
