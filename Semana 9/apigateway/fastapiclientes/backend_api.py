import os
import secrets

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Depends
)
app = FastAPI(
    title = "Protected Backend API clientes",
    description = "API ubicada en el localhost enruta por API gateway /api/clientes"
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
        "/clientes",
        dependencies=[Depends(verify_gateway)]
        )
def clientes(
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
        "clientes": [
            {"id": 1, "nombre": "Juan Perez", "correo": "juan.perez@example.com"},
            {"id": 2, "nombre": "Maria Gomez", "correo": "maria.gomez@example.com"},
            {"id": 3, "nombre": "Benjamin Rodriguez", "correo": "carlos.rodriguez@example.com"},
            {"id": 4, "nombre": "Ana Martinez", "correo": "ana.martinez@example.com"},
            {"id": 5, "nombre": "Luis Fernandez", "correo": "luis.fernandez@example.com"},
            {"id": 6, "nombre": "Sofia Lopez", "correo": "sofia.lopez@example.com"},
            {"id": 7, "nombre": "Diego Sanchez", "correo": "diego.sanchez@example.com"},
            {"id": 8, "nombre": "Valentina Torres", "correo": "valentina.torres@example.com"}
        ]
    }
