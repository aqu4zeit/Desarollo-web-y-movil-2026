workspace "AROMA" "Aroma & Cafe" {

    !identifiers hierarchical

    model {
        visitante = person "Visitante" "Persona que consulta el menu y la informacion de la cafeteria sin iniciar sesion."
        cliente = person "Cliente" "Persona autenticada que compra productos y sigue sus pedidos."
        operador = person "Operador" "Personal de la cafeteria: administrador, dueno, cajero y encargado de despacho."

        proveedorMensajeria = softwareSystem "Proveedor de mensajeria" "Valida correos y envia los codigos de verificacion y las boletas." {
            tags "SistemaExterno"
        }

        plataformaPago = softwareSystem "Plataforma de pago" "Cobra los pedidos y avisa el resultado con un aviso firmado." {
            tags "SistemaExterno"
        }

        sistema = softwareSystem "Aroma & Cafe" "Tienda en linea de la cafeteria: catalogo, clientes, pedidos, pagos y despacho." {
            tags "SistemaEvaluado"

            frontend = container "Frontend responsivo" "Pagina publica de la cafeteria: inicio, galeria, menu, nosotros y contacto. Por ahora usa sus datos locales y aun no se conecta al API Gateway." "HTML, CSS y JavaScript" {
                tags "Frontend"
            }

            apiGateway = container "API Gateway" "Punto de entrada al backend; valida la sesion, aplica el rol de cada ruta y enruta las peticiones." "FastAPI" {
                tags "Gateway"
            }

            authService = container "Auth Service" "Autentica usuarios, emite tokens de 15 minutos y responde la introspeccion y el cierre de sesion." "FastAPI" {
                tags "Seguridad"
            }

            secretManager = container "Administrador de secretos" "Guarda un secreto por cada tramo entre servicios y los entrega solo a consumidores autorizados." "HashiCorp Vault" {
                tags "Seguridad"
            }

            inventory = container "inventory" "Gestiona el catalogo de cafes y reposteria, el stock y las reservas de stock." "FastAPI" {
                tags "Privado"
            }

            clients = container "clients" "Gestiona el registro y perfil del cliente, la verificacion del correo, promociones y contacto." "FastAPI" {
                tags "Privado"
            }

            orders = container "orders" "Gestiona el ciclo de vida de los pedidos, sus estados y la anulacion con motivo." "FastAPI" {
                tags "Privado"
            }

            payments = container "payments" "Gestiona los pagos, las ventas de la caja web y las boletas." "FastAPI" {
                tags "Privado"
            }

            despacho = container "despacho" "Gestiona las ordenes de despacho, la cobertura de 3 km y los choferes." "FastAPI" {
                tags "Privado"
            }

            graphqlGateway = container "GraphQL Gateway" "Expone mis pedidos y el reporte de ventas agregando informacion de los subsistemas." "Apollo Server" {
                tags "Gateway"
            }

            dbInventory = container "Datos de inventario" "Persistencia del subsistema inventory." "MongoDB" {
                tags "BaseDatos"
            }

            dbClients = container "Datos de clientes" "Persistencia del subsistema clients." "MongoDB" {
                tags "BaseDatos"
            }

            dbOrders = container "Datos de pedidos" "Persistencia del subsistema orders." "MongoDB" {
                tags "BaseDatos"
            }

            dbPayments = container "Datos de pagos" "Persistencia del subsistema payments." "MongoDB" {
                tags "BaseDatos"
            }

            dbDespacho = container "Datos de despacho" "Persistencia del subsistema despacho." "MongoDB" {
                tags "BaseDatos"
            }

            dbIdentity = container "Datos de identidad" "Persistencia de usuarios, perfiles y sesiones." "MongoDB" {
                tags "BaseDatos"
            }
        }

        // Relaciones de contexto (C1).
        visitante -> sistema "Consulta el menu y la informacion de la cafeteria"
        cliente -> sistema "Compra productos y sigue sus pedidos"
        operador -> sistema "Administra catalogo, ventas y despachos"
        cliente -> plataformaPago "Paga el pedido en la pagina de pago" "Navegador web"
        sistema -> proveedorMensajeria "Envia correos de verificacion y boletas"
        sistema -> plataformaPago "Solicita el cobro de los pedidos"


        // Relaciones entre los actores y el contenedor web; y entre contenedores.
        visitante -> sistema.frontend "Consulta el menu y la informacion de la cafeteria" "Navegador web"
        cliente -> sistema.frontend "Revisa el menu y la informacion de la cafeteria" "Navegador web"
        visitante -> sistema.apiGateway "Consulta el catalogo y envia mensajes de contacto" "HTTP/JSON"
        cliente -> sistema.apiGateway "Se registra, compra, paga y revisa sus pedidos" "HTTP/JSON"
        operador -> sistema.apiGateway "Gestiona catalogo, usuarios, ventas, despachos y reporte" "HTTP/JSON"
        sistema.apiGateway -> sistema.authService "Inicia sesion, valida el token y administra usuarios" "HTTP/JSON"
        sistema.apiGateway -> sistema.inventory "Enruta catalogo y stock" "HTTP/JSON"
        sistema.apiGateway -> sistema.clients "Enruta registro y perfil de clientes" "HTTP/JSON"
        sistema.apiGateway -> sistema.orders "Enruta operaciones de pedidos" "HTTP/JSON"
        sistema.apiGateway -> sistema.payments "Enruta pagos y boletas" "HTTP/JSON"
        sistema.apiGateway -> sistema.despacho "Enruta ordenes de despacho" "HTTP/JSON"
        sistema.apiGateway -> sistema.graphqlGateway "Enruta consultas GraphQL" "HTTP/GraphQL"
        sistema.clients -> sistema.authService "Crea y activa la cuenta del cliente" "HTTP/JSON"
        sistema.clients -> proveedorMensajeria "Valida el correo y envia el codigo de verificacion" "HTTP/JSON"
        sistema.orders -> sistema.clients "Consulta los datos de entrega del cliente" "HTTP/JSON"
        sistema.orders -> sistema.inventory "Reserva y libera stock" "HTTP/JSON"
        sistema.orders -> sistema.despacho "Consulta cobertura y crea o anula la orden de despacho" "HTTP/JSON"
        sistema.orders -> sistema.payments "Solicita el reembolso de un pedido anulado" "HTTP/JSON"
        sistema.payments -> sistema.orders "Consulta el pedido y lo marca como pagado" "HTTP/JSON"
        sistema.payments -> plataformaPago "Crea el cobro y solicita reembolsos" "HTTP/JSON"
        sistema.payments -> proveedorMensajeria "Envia la boleta al cliente" "HTTP/JSON"
        plataformaPago -> sistema.apiGateway "Notifica el resultado del pago" "HTTP/JSON"
        sistema.despacho -> sistema.orders "Actualiza el estado del pedido" "HTTP/JSON"
        sistema.graphqlGateway -> sistema.orders "Agrega informacion de pedidos" "HTTP/JSON"
        sistema.graphqlGateway -> sistema.payments "Agrega pagos y ventas" "HTTP/JSON"
        sistema.graphqlGateway -> sistema.inventory "Agrega informacion de productos" "HTTP/JSON"
        sistema.graphqlGateway -> sistema.despacho "Agrega el estado de los despachos" "HTTP/JSON"
        sistema.apiGateway -> sistema.secretManager "Obtiene los secretos de sus tramos" "Canal autenticado"
        sistema.authService -> sistema.secretManager "Obtiene secretos autorizados" "Canal autenticado"
        sistema.inventory -> sistema.secretManager "Obtiene secretos y credenciales de su base" "Canal autenticado"
        sistema.clients -> sistema.secretManager "Obtiene secretos y credenciales de su base" "Canal autenticado"
        sistema.orders -> sistema.secretManager "Obtiene secretos y credenciales de su base" "Canal autenticado"
        sistema.payments -> sistema.secretManager "Obtiene secretos y credenciales para integraciones" "Canal autenticado"
        sistema.despacho -> sistema.secretManager "Obtiene secretos y credenciales de su base" "Canal autenticado"
        sistema.graphqlGateway -> sistema.secretManager "Obtiene los secretos de sus tramos" "Canal autenticado"
        sistema.inventory -> sistema.dbInventory "Lee y escribe productos y reservas" "Acceso a datos"
        sistema.clients -> sistema.dbClients "Lee y escribe perfiles de clientes" "Acceso a datos"
        sistema.orders -> sistema.dbOrders "Lee y escribe pedidos" "Acceso a datos"
        sistema.payments -> sistema.dbPayments "Lee y escribe pagos y boletas" "Acceso a datos"
        sistema.despacho -> sistema.dbDespacho "Lee y escribe ordenes de despacho" "Acceso a datos"
        sistema.authService -> sistema.dbIdentity "Consulta y actualiza identidades" "Acceso a datos"
    }

    views {
        systemContext sistema "C1_Contexto" "Contexto de negocio: actores y dependencias externas." {
            title "C1 - Contexto de Aroma & Cafe"
            include *
            autoLayout lr
        }

        container sistema "C2_Contenedores" "Aplicaciones y almacenes de datos de Aroma & Cafe." {
            title "C2 - Contenedores de Aroma & Cafe"
            include *
            autoLayout lr
        }

        // Vistas adicionales: son recortes del mismo modelo, NO otros sistemas.
        container sistema "C2_Catalogo" "Recorrido estructural relacionado con la consulta del menu." {
            include visitante cliente sistema.frontend sistema.apiGateway sistema.inventory sistema.dbInventory
            autoLayout lr
        }

        container sistema "C2_Pedidos" "Recorrido estructural relacionado con el registro de pedidos." {
            include cliente sistema.apiGateway sistema.authService sistema.orders sistema.clients sistema.inventory sistema.despacho sistema.payments plataformaPago sistema.dbOrders sistema.dbInventory sistema.dbDespacho sistema.dbPayments
            autoLayout lr
        }

        styles {
            element "Person" {
                shape person
                background #56718A
                color #FFFFFF
            }
            element "Software System" {
                shape roundedbox
                background #0C527A
                color #FFFFFF
            }
            element "SistemaEvaluado" {
                background #173B5D
                color #FFFFFF
            }
            element "Container" {
                shape roundedbox
                background #E3ECF5
                color #173B5D
            }
            element "Frontend" {
                shape webbrowser
                background #CDE5F7
                color #153E5B
            }
            element "Gateway" {
                background #2B6289
                color #FFFFFF
            }
            element "Seguridad" {
                background #3F6171
                color #FFFFFF
            }
            element "Privado" {
                background #D5E8EF
                color #173B5D
            }
            element "BaseDatos" {
                shape cylinder
                background #E5EAF0
                color #243F56
            }
            element "SistemaExterno" {
                background #F1EDE7
                color #544633
                stroke #A89D8A
            }
            relationship "Relationship" {
                color #60758A
                thickness 2
            }
        }
    }
}
