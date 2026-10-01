# Semana 9 — Authentication Service con FastAPI, API Gateway y Vault

Servicio de autenticación construido con **FastAPI** que emite tokens con tiempo de expiración, permite consultar su estado (introspección) y cerrar sesión. El **API Gateway** valida cada Bearer token consultando la introspección del Authentication Service y enruta las solicitudes hacia dos servicios backend independientes: uno de clientes y otro de productos. Los secretos entre servicios se administran con **HashiCorp Vault**, y el gateway propaga la identidad del usuario (`X-Authenticated-User`, `X-Authenticated-Roles`) hacia el backend.

## Estructura

```
apigateway/
├── auth-service/         # Authentication Service (puerto 8100)
│   └── auth-service.py
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
vault kv put secret/gateway auth_introspection_secret=gateway-auth-secret-789 backend_shared_secret=gateway-api-secret-456
```

Cada servicio corre en su propia terminal, con el entorno activado (`conda activate apigateway`):

**Authentication Service** (puerto 8100):

```powershell
cd auth-service
$env:AUTH_INTROSPECTION_SECRET="gateway-auth-secret-789"
uvicorn auth-service:app --host 0.0.0.0 --port 8100
```

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
$env:AUTH_SERVICE_URL="http://127.0.0.1:8100"
uvicorn gateway:app --host 0.0.0.0 --port 8000
```

## Usuarios de prueba

| Usuario | Contraseña | Rol |
|---|---|---|
| ana | 1234 | user |
| pedro | 5678 | user |
| ernesto | admin123 | user, admin |

Los tokens tienen una vigencia de 15 minutos.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/login` (puerto 8100) | Inicia sesión y entrega el access token — requiere `X-Gateway-Auth-Secret` |
| POST | `/introspect` (puerto 8100) | Estado del token (activo, usuario, roles, expiración) — requiere `X-Gateway-Auth-Secret` |
| POST | `/logout` (puerto 8100) | Cierra la sesión del token — requiere `X-Gateway-Auth-Secret` |
| GET | `/health` (puerto 8100) | Estado del servicio — requiere `X-Gateway-Auth-Secret` |
| GET | `/clientes` (puerto 9000) | Lista de clientes — requiere `X-Gateway-Secret` |
| GET | `/api/clientes` (puerto 8000) | Lista de clientes — vía Gateway, requiere Bearer token |
| GET | `/api/productos` (puerto 8000) | Lista de productos — vía Gateway, requiere Bearer token |

## Prueba rápida

Iniciar sesión y obtener el token:

```bash
curl -X POST http://localhost:8100/login -H "Content-Type: application/json" -H "X-Gateway-Auth-Secret: gateway-auth-secret-789" -d "{\"username\": \"ana\", \"password\": \"1234\"}"
```

Usar el `access_token` recibido:

```bash
curl -X POST http://localhost:8100/introspect -H "Content-Type: application/json" -H "X-Gateway-Auth-Secret: gateway-auth-secret-789" -d "{\"token\": \"<access_token>\"}"
curl http://localhost:8000/api/clientes
curl -H "Authorization: Bearer <access_token>" http://localhost:8000/api/clientes
curl -X POST http://localhost:8100/logout -H "Content-Type: application/json" -H "X-Gateway-Auth-Secret: gateway-auth-secret-789" -d "{\"token\": \"<access_token>\"}"
curl -H "Authorization: Bearer <access_token>" http://localhost:8000/api/clientes
```
