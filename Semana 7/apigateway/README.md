# Semana 7 — API Gateway con FastAPI

API Gateway local construido con **FastAPI** y **httpx**, que enruta solicitudes hacia dos servicios backend independientes: uno de clientes y otro de productos.

## Estructura

```
apigateway/
├── gateway/              # API Gateway (puerto 8000)
│   └── gateway.py
└── fastapiclientes/       # Backend de clientes (puerto 9000)
    └── backend_api.py
```

> El backend de productos (`fastapiproductos`, puerto 9100) lo mantiene otro integrante del equipo en su propia carpeta/rama.

## Requisitos

- Python 3.11
- Anaconda (o cualquier gestor de entornos virtuales)

## Creación del entorno

```bash
conda create -n apigateway python=3.11 -y
conda activate apigateway
pip install -r requirements.txt
```

## Ejecución

Cada servicio corre en su propia terminal, con el entorno activado (`conda activate apigateway`):

**Backend de clientes** (puerto 9000):

```bash
cd fastapiclientes
uvicorn backend_api:app --host 0.0.0.0 --port 9000
```

**API Gateway** (puerto 8000):

```bash
cd gateway
uvicorn gateway:app --host 0.0.0.0 --port 8000
```

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/clientes` (puerto 9000) | Lista de clientes — backend directo |
| GET | `/api/clientes` (puerto 8000) | Lista de clientes — vía Gateway |
| GET | `/api/productos` (puerto 8000) | Lista de productos — vía Gateway |

## Prueba rápida

```bash
curl http://localhost:9000/clientes
curl http://localhost:8000/api/clientes
```
