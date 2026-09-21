from fastapi import FastAPI

app = FastAPI(
    title = "API de productos",
    description = "API ubicada en el localhost enrutada por el API gateway /api/productos"
)

@app.get("/health")
def salud():
    return {
        "estado": "OK",
        "servicio": "API de Productos"
    }

@app.get("/productos")
def productos():
    return {
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
