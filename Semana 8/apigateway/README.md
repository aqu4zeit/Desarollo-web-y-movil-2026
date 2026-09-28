# Semana 8 — API Gateway seguro con FastAPI y Vault

API Gateway local construido con **FastAPI** y **httpx**, que enruta solicitudes hacia dos servicios backend independientes: uno de clientes y otro de productos. Los secretos se administran con **HashiCorp Vault**: el gateway valida el Bearer token del cliente y envía un secreto interno (`X-Gateway-Secret`) al backend, que rechaza cualquier solicitud que no venga desde el gateway.

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
- HashiCorp Vault

## Creación del entorno

```bash
conda create -n apigateway python=3.11 -y
conda activate apigateway
pip install -r requirements.txt
```

## Ejecución

**Vault** (PowerShell):

```powershell
vault server -dev -dev-root-token-id="dev-only-token"
```

En otra PowerShell se cargan los secretos:

```powershell
$env:VAULT_ADDR="http://127.0.0.1:8200"
$env:VAULT_TOKEN="dev-only-token"
vault status
vault kv put secret/gateway client_token=student-token-123 backend_shared_secret=gateway-api-secret-456
```

Cada servicio corre en su propia terminal, con el entorno activado (`conda activate apigateway`):

**Backend de clientes** (puerto 9000):

```powershell
cd fastapiclientes
$env:INTERNAL_GATEWAY_SECRET="gateway-api-secret-456"
uvicorn backend_api:app --host 0.0.0.0 --port 9000
```

**API Gateway** (puerto 8000):

```powershell
cd gateway
$env:VAULT_ADDR="http://127.0.0.1:8200"
$env:VAULT_TOKEN="dev-only-token"
uvicorn gateway:app --host 0.0.0.0 --port 8000
```

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/clientes` (puerto 9000) | Lista de clientes — requiere `X-Gateway-Secret` |
| GET | `/api/clientes` (puerto 8000) | Lista de clientes — vía Gateway, requiere Bearer token |
| GET | `/api/productos` (puerto 8000) | Lista de productos — vía Gateway, requiere Bearer token |

## Prueba rápida

```bash
curl http://localhost:9000/clientes
curl -H "X-Gateway-Secret: gateway-api-secret-456" http://localhost:9000/clientes
curl http://localhost:8000/api/clientes
curl -H "Authorization: Bearer student-token-123" http://localhost:8000/api/clientes
```
