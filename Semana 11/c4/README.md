# Semana 11 — Modelo C4 de Aroma & Café (contexto y contenedores)

Modelo de arquitectura de **Aroma & Café** escrito en **Structurizr DSL** siguiendo el modelo **C4**. La vista de contexto (C1) muestra a los actores y los sistemas externos con los que se comunica la tienda; la vista de contenedores (C2) muestra las aplicaciones, servicios y bases de datos que la componen y cómo se relacionan entre sí.

## Estructura

```
c4/
└── workspace.dsl     # Modelo, vistas y estilos
```

## Requisitos

- Docker Desktop (para Structurizr local), o un navegador para el playground de Structurizr

## Ejecución

**Structurizr local** (PowerShell, dentro de la carpeta `c4`):

```powershell
docker pull structurizr/structurizr
docker run -it --rm -p 8080:8080 -v "${PWD}:/usr/local/structurizr" structurizr/structurizr local
```

Luego entrar a http://localhost:8080

También se puede pegar el contenido de `workspace.dsl` en https://playground.structurizr.com y presionar el botón de renderizar.

## Vistas

| Vista | Nivel | Qué muestra |
|---|---|---|
| `C1_Contexto` | C1 | Actores, la tienda y los sistemas externos |
| `C2_Contenedores` | C2 | Todos los contenedores y sus relaciones |
| `C2_Catalogo` | C2 | Recorrido de la consulta del menú |
| `C2_Pedidos` | C2 | Recorrido del registro de un pedido |

## Actores y sistemas externos

| Elemento | Descripción |
|---|---|
| Visitante | Consulta el menú y la información de la cafetería sin iniciar sesión |
| Cliente | Compra productos y sigue sus pedidos |
| Operador | Personal de la cafetería: administrador, dueño, cajero y encargado de despacho |
| Proveedor de mensajería | Valida correos y envía los códigos de verificación y las boletas |
| Plataforma de pago | Cobra los pedidos y avisa el resultado con un aviso firmado |

La plataforma de pago y el proveedor de mensajería se representan como sistemas externos; en el backend corren como adaptadores de prueba (`proveedor_pago` y `mensajeria`).

## Contenedores

| Contenedor | Tecnología | Descripción |
|---|---|---|
| Frontend responsivo | HTML, CSS y JavaScript | Página pública de la cafetería (inicio, galería, menú, nosotros y contacto); por ahora usa sus datos locales y aún no se conecta al API Gateway |
| API Gateway | FastAPI | Punto de entrada al backend: valida la sesión, aplica el rol de cada ruta y enruta las peticiones |
| Auth Service | FastAPI | Autentica usuarios, emite tokens de 15 minutos y responde la introspección y el cierre de sesión |
| Administrador de secretos | HashiCorp Vault | Guarda un secreto por cada tramo entre servicios y los entrega solo a consumidores autorizados |
| GraphQL Gateway | Apollo Server | Expone mis pedidos y el reporte de ventas agregando información de los subsistemas |
| inventory | FastAPI | Catálogo de cafés y repostería, stock y reservas de stock |
| clients | FastAPI | Registro y perfil del cliente, verificación del correo, promociones y contacto |
| orders | FastAPI | Ciclo de vida de los pedidos, sus estados y la anulación con motivo |
| payments | FastAPI | Pagos, ventas de la caja web y boletas |
| despacho | FastAPI | Órdenes de despacho, cobertura de 3 km y choferes |
| Datos de inventario, clientes, pedidos, pagos, despacho e identidad | MongoDB | Una base por cada servicio |

## Relaciones principales

- Visitantes y clientes ven el menú y la información de la cafetería en el **Frontend**, que todavía funciona con sus datos locales.
- Visitantes, clientes y operadores usan el backend a través del **API Gateway** (HTTP/JSON), única entrada pública junto con la página de pago.
- El **API Gateway** inicia sesión, valida el token y administra usuarios con el **Auth Service**, y enruta cada petición a un solo servicio (`inventory`, `clients`, `orders`, `payments`, `despacho`) o al **GraphQL Gateway**.
- El **GraphQL Gateway** combina información de `orders`, `payments`, `inventory` y `despacho` para "mis pedidos" y el reporte de ventas.
- `orders` coordina el pedido: consulta al cliente en `clients`, reserva stock en `inventory`, consulta la cobertura y crea la orden en `despacho`, y pide reembolsos a `payments` cuando se anula.
- `payments` crea el cobro en la **Plataforma de pago**, que avisa el resultado al API Gateway; luego marca el pedido como pagado en `orders` y envía la boleta por el **Proveedor de mensajería**.
- Cada servicio obtiene sus secretos del **Administrador de secretos** y guarda sus datos en su propia base.
