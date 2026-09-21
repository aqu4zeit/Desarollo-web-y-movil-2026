from fastapi import FastAPI
import httpx

app = FastAPI(title = "Local API Gateway")

BACKEND_URL = "http://localhost:9000" # fastapi - clientes
BACKEND_URL2 = "http://localhost:9100" # fastapi2 - productos

# http://localhost:8000/api/clientes
@app.get("/api/clientes")
async def clientes():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_URL}/clientes" # http://localhost:9000/clientes
        )
    return response.json()

# http://localhost:8000/api/productos
@app.get("/api/productos")
async def productos():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_URL2}/productos" # http://localhost:9100/productos
        )
    return response.json()
