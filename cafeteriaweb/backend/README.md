# Aroma & Café — Backend

Backend seguro de la tienda en línea (Evaluación 2). Todo corre en Docker; solo el API Gateway (puerto 8000)
y la pasarela de pago de prueba (puerto 9500) se ven desde fuera.

## Servicios

| Carpeta | Puerto interno | Qué hace |
|---|---|---|
| `gateway` | 8000 (publicado) | API Gateway: rutas explícitas con su rol, sesión por cookie HttpOnly, límite de solicitudes |
| `auth` | 8100 | Authentication Service: login, introspección, logout, usuarios y perfiles |
| `inventory` | 9100 | Catálogo, stock y reservas de stock |
| `clients` | 9000 | Registro y perfil del cliente, verificación del correo, promociones y contacto |
| `orders` | 9200 | Pedidos y sus estados, anulación con motivo |
| `payments` | 9300 | Pagos, ventas de la caja web y boletas |
| `despacho` | 9400 | Órdenes de despacho, cobertura de 3 km y choferes |
| `graphql` | 8090 | GraphQL Gateway privado: mis pedidos y reporte de ventas |
| `mensajeria` | 9600 | API de mensajería **de prueba** (valida correos y guarda los mensajes en un buzón) |
| `proveedor_pago` | 9500 (publicado) | Pasarela de pago **de prueba** (página de pago, aviso firmado, reembolso) |
| Vault, MongoDB | 8200, 27017 | Secretos por servicio y una base por servicio |

## Requisitos

- Docker Desktop (con Docker Compose)
- PowerShell

## Iniciar y detener

```
cd backend
.\preparar.ps1
```

`preparar.ps1` genera el archivo `.env` con claves aleatorias (queda fuera de Git; ver `.env.ejemplo`), carga en
Vault un secreto por cada tramo entre servicios, crea un usuario de MongoDB por servicio, crea una política y un
token de Vault por servicio y levanta todo. La API queda en http://localhost:8000/api y el GraphQL Gateway
en http://localhost:8000/graphql (ver `GET /health`).

Vault corre en modo desarrollo (en memoria): si su contenedor se reinicia, se vuelve a ejecutar `preparar.ps1`.

| Acción | Comando |
|---|---|
| Ver el estado | `docker compose ps` |
| Detener (conserva los datos) | `docker compose down` |
| Detener y borrar los datos | `docker compose down -v` |
| Ver los correos de prueba (código de verificación, boletas) | `.\ver-correos.ps1 correo@ejemplo.cl` |

## Usuarios de prueba

| Usuario | Clave | Perfil |
|---|---|---|
| admin@aroma.cl | Admin2026! | Administrador |
| dueno@aroma.cl | Dueno2026! | Dueño (reporte de ventas) |
| cajero@aroma.cl | Cajero2026! | Cajero virtual |
| despacho@aroma.cl | Despacho2026! | Encargado de despacho |
| camila@aroma.cl | Camila2026! | Cliente |

## Pruebas

| Pruebas | Comando |
|---|---|
| Unitarias de un servicio (MongoDB local en 27017) | `cd orders` y `python -m pytest -q` |
| GraphQL Gateway | `cd graphql`, `npm ci` y `node --test tests/graphql.test.js` |
| Integración del sistema completo (con Docker levantado) | `python -m pytest e2e/test_stack.py -q` |
| Carga | ver la cabecera de `e2e/prueba_carga.py` |

## Conexión con el frontend

En esta entrega el backend funciona solo: la página (`index.html`) todavía usa sus datos locales. Para conectarla:

1. Montar la carpeta de la página en el gateway (`FRONTEND_DIR` y `StaticFiles`), así página y API quedan en el mismo
   origen y la cookie de sesión funciona sin CORS.
2. Cambiar `URL_RETORNO` de `payments` a la página del cliente, que lee `?pedido=` al volver de la pasarela.
3. Reemplazar los datos locales de `app.js` por llamadas `fetch` a las rutas de la tabla del gateway.

## De dónde salió cada parte

| Parte | Base | Qué se agregó |
|---|---|---|
| Microservicios (FastAPI + Motor + MongoDB) | CRUD de la Semana 6 (`lifespan`, Pydantic, `ObjectId`, `q/skip/limit`) | Una base y un usuario por servicio, reglas del negocio, índices y datos de prueba |
| Protección de cada servicio | Semana 8 y guía "API Gateway + Vault + FastAPI" (`X-Gateway-Secret`, `secrets.compare_digest`) | Un secreto distinto por cada tramo origen-destino, leído de Vault |
| API Gateway | Semanas 7 a 9 (httpx, Vault, Bearer, `X-Authenticated-*`) | Lista explícita de rutas con su rol, límite por IP, tiempos de espera, `X-Correlation-Id` |
| Sesión del navegador | Guía "Autenticación y autorización" (`/auth/login`, `/auth/me`, `/auth/logout`, cookie HttpOnly, `fetch` con `credentials`) | — |
| Auth Service | Semana 9 (login, introspección, logout, 15 minutos) | Claves con [Argon2](https://pypi.org/project/argon2-cffi/) (la guía lo nombra), usuarios y sesiones en MongoDB |
| GraphQL Gateway | Semana 5 (Apollo Server + Express, `gql`, resolvers) | Sin base de datos: los resolvers llaman a las APIs internas; límites de profundidad y costo, batching |
| Docker Compose y Vault en contenedor | Guía "Autenticación y autorización" y guía de Vault (`hashicorp/vault`) | Redes pública, privada y de proveedores; health checks |
| Pruebas | Guía "Autenticación y autorización" (pytest) | Pruebas de propiedad, pagos duplicados, stock, GraphQL y carga |
| Pasarela de pago y mensajería | La pauta permite adaptadores de prueba si no hay un proveedor real | Firma HMAC del aviso, reintentos y reembolso; buzón de correo de prueba |

El GraphQL Gateway usa Express 4.21.2 en vez de 5.2.1 (Semana 5) porque Apollo Server 3 solo acepta Express 4; en la
Semana 5 se instaló con yarn, que no lo revisa.
