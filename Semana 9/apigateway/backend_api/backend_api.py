import os
import secrets

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Depends
)
app = FastAPI(
    title = "Protected Backend API productos",
    description = "API ubicada en el localhost enruta por API gateway /api/productos"
)

#SELINUX
INTERNAL_GATEWAY_SECRET = os.getenv(
    "INTERNAL_GATEWAY_SECRET"
)

if not INTERNAL_GATEWAY_SECRET:
    raise RuntimeError(
        "INTERNAL_GATEWAY_SECRET no está configurado"
    )

def verify_gateway(
        x_gateway_secret: str = Header(default="")
):
    valid = secrets.compare_digest(
        x_gateway_secret,
        INTERNAL_GATEWAY_SECRET
    )
    if not valid:
        raise HTTPException(
            status_code=403,
            detail="Solicitud no autorizada desde gateway"
        )


@app.get(
        "/health",
        dependencies=[Depends(verify_gateway)]
        )
def health(
    x_authenticated_client: str | None = Header(
        default=None
    )
):
    return {
        "authenticated_client": x_authenticated_client,
        "status": "OK",
        "service": "Backend API"
    }
@app.get(
        "/productos",
        dependencies=[Depends(verify_gateway)]
        )
def productos(
    x_authenticated_client: str | None = Header(default=None),
    x_authenticated_user: str | None = Header(default=None),
    x_authenticated_roles: str | None = Header(default=None)
):
    return {
        "identity": {
            "client_id": x_authenticated_client,
            "username": x_authenticated_user,
            "roles": x_authenticated_roles
        },
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
