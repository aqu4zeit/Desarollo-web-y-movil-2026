from fastapi import FastAPI

app = FastAPI(
    title = "API de clientes",
    description = "API ubicada en el localhost enrutada por el API gateway /api/clientes"
)

@app.get("/health")
def salud():
    return {
        "estado": "OK",
        "servicio": "API de Clientes"
    }

@app.get("/clientes")
def clientes():
    return {
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
