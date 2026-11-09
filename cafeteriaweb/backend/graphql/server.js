const crypto = require('crypto');
const express = require('express');
const { ApolloServer, gql, ApolloError, AuthenticationError, ForbiddenError, UserInputError } = require('apollo-server-express');
const { GraphQLError, Kind } = require('graphql');

// GraphQL Gateway privado de Aroma & Café (base: Semana 5, Apollo Server + Express).
// No accede a ninguna base de datos: compone respuestas llamando a las APIs
// internas de orders, payments, inventory y despacho, cada una con su secreto.

const VAULT_ADDR = process.env.VAULT_ADDR || 'http://127.0.0.1:8200';
const VAULT_TOKEN = process.env.VAULT_TOKEN;
const URLS = {
    orders: process.env.ORDERS_URL || 'http://127.0.0.1:9200',
    payments: process.env.PAYMENTS_URL || 'http://127.0.0.1:9300',
    inventory: process.env.INVENTORY_URL || 'http://127.0.0.1:9100',
    despacho: process.env.DESPACHO_URL || 'http://127.0.0.1:9400'
};

const PROFUNDIDAD_MAXIMA = 6;
const COSTO_MAXIMO = 150;       // campos solicitados por consulta
const MAXIMO_POR_PAGINA = 50;
const PLAZO_MS = 3000;          // plazo maximo de cada llamada interna
const PERSONAL = ['admin', 'cajero', 'despacho', 'dueno'];
// Quienes pueden ver los datos personales y de despacho del cliente de un pedido
const VEN_DATOS_CLIENTE = ['admin', 'cajero', 'despacho'];

const typeDefs = gql`
    type Producto{
        id: ID!
        nombre: String!
        precio: Int!
        imagen: String
        disponible: Boolean!
    }

    type ItemPedido{
        nombre: String!
        precio: Int!
        cantidad: Int!
        subtotal: Int!
        producto: Producto
    }

    type DatosCliente{
        nombre: String!
        direccion: String!
        comuna: String!
        telefono: String!
    }

    type Pago{
        id: ID!
        estado: String!
        monto: Int!
        folioBoleta: Int
    }

    type Despacho{
        numero: Int!
        estado: String!
        chofer: String
    }

    type Evento{
        estado: String!
        fecha: String!
    }

    type Pedido{
        id: ID!
        estado: String!
        total: Int!
        creado: String!
        motivoAnulacion: String
        items: [ItemPedido!]!
        historial: [Evento!]!
        cliente: DatosCliente
        pago: Pago
        despacho: Despacho
    }

    type ProductoVendido{
        nombre: String!
        cantidad: Int!
        total: Int!
    }

    type ConteoEstado{
        estado: String!
        cantidad: Int!
    }

    type ResumenVentas{
        desde: String!
        hasta: String!
        cantidadVentas: Int!
        totalVendido: Int!
        ticketPromedio: Int!
        ventasAnuladas: Int!
        productos: [ProductoVendido!]!
        pedidosPorEstado: [ConteoEstado!]
    }

    type Query{
        misPedidos(primeros: Int = 10, saltar: Int = 0): [Pedido!]!
        pedido(id: ID!): Pedido
        resumenVentas(desde: String!, hasta: String!): ResumenVentas
    }
`;

// Autorizacion

function exigirSesion(ctx) {
    if (!ctx.usuario.user_id) {
        throw new AuthenticationError('Se requiere una sesión válida');
    }
}

function tieneRol(ctx, roles) {
    return roles.some((rol) => ctx.usuario.roles.includes(rol));
}

function exigirRol(ctx, roles) {
    exigirSesion(ctx);
    if (!tieneRol(ctx, roles)) {
        throw new ForbiddenError('El usuario no tiene permisos para esta consulta');
    }
}

// Batching: cada dato relacionado se pide UNA vez por consulta para todos los
// pedidos de la respuesta, no una vez por pedido.
function lote(ctx, tipo) {
    if (!ctx.lotes[tipo]) {
        const ids = ctx.pedidoIds.join(',');
        const consultas = {
            pagos: () => ctx.llamar('payments', '/interno/pagos', { pedido_ids: ids }),
            despachos: () => ctx.llamar('despacho', '/interno/ordenes', { pedido_ids: ids }),
            productos: () => ctx.llamar('inventory', '/productos', { ids: ctx.productoIds.join(','), limit: 200 })
                .then((lista) => Object.fromEntries(lista.map((p) => [p.id, p])))
        };
        ctx.lotes[tipo] = consultas[tipo]();
    }
    return ctx.lotes[tipo];
}

function registrarPedidos(ctx, pedidos) {
    ctx.pedidoIds = pedidos.map((p) => p.id);
    ctx.productoIds = [...new Set(pedidos.flatMap((p) => p.items.map((i) => i.producto_id)))];
    return pedidos;
}

function validarFecha(texto, nombre) {
    const fecha = new Date(texto);
    if (Number.isNaN(fecha.getTime())) {
        throw new UserInputError(`Fecha inválida en ${nombre}`);
    }
    return fecha;
}

const resolvers = {
    Query: {
        async misPedidos(obj, { primeros, saltar }, ctx) {
            exigirRol(ctx, ['cliente']);
            if (primeros < 1 || primeros > MAXIMO_POR_PAGINA || saltar < 0) {
                throw new UserInputError(`primeros debe estar entre 1 y ${MAXIMO_POR_PAGINA}`);
            }
            const pedidos = await ctx.llamar('orders', '/interno/pedidos', {
                user_id: ctx.usuario.user_id, limit: primeros, skip: saltar
            });
            return registrarPedidos(ctx, pedidos);
        },
        async pedido(obj, { id }, ctx) {
            exigirSesion(ctx);
            let pedido;
            try {
                pedido = await ctx.llamar('orders', `/interno/pedidos/${encodeURIComponent(id)}`);
            } catch (error) {
                if (error.extensions && error.extensions.status === 404) {
                    return null;
                }
                throw error;
            }
            // Autorizacion por recurso: un cliente solo ve sus pedidos
            if (pedido.user_id !== ctx.usuario.user_id && !tieneRol(ctx, PERSONAL)) {
                return null;
            }
            registrarPedidos(ctx, [pedido]);
            return pedido;
        },
        // RF 9: reporte de ventas por periodo para el dueno (y el administrador)
        async resumenVentas(obj, { desde, hasta }, ctx) {
            exigirRol(ctx, ['dueno', 'admin']);
            const inicio = validarFecha(desde, 'desde');
            const fin = validarFecha(hasta, 'hasta');
            if (inicio > fin || fin - inicio > 366 * 24 * 3600 * 1000) {
                throw new UserInputError('El período debe ser válido y de máximo un año');
            }
            const ventas = await ctx.llamar('payments', '/ventas', {
                desde: inicio.toISOString(), hasta: fin.toISOString(), limit: 500
            });
            return { desde: inicio.toISOString(), hasta: fin.toISOString(), ventas };
        }
    },
    Pedido: {
        creado: (p) => p.creado,
        motivoAnulacion: (p) => p.motivo_anulacion,
        historial: (p) => p.historial.map((h) => ({ estado: h.estado, fecha: h.fecha })),
        // Autorizacion por campo: el dueno ve pedidos, pero no los datos personales
        cliente(p, args, ctx) {
            if (p.user_id !== ctx.usuario.user_id && !tieneRol(ctx, VEN_DATOS_CLIENTE)) {
                throw new ForbiddenError('Sin permiso para ver los datos del cliente');
            }
            return p.cliente;
        },
        async pago(p, args, ctx) {
            const pagos = await lote(ctx, 'pagos');
            const pago = pagos[p.id];
            return pago ? { id: pago.id, estado: pago.estado, monto: pago.monto, folioBoleta: pago.folio_boleta } : null;
        },
        async despacho(p, args, ctx) {
            const despachos = await lote(ctx, 'despachos');
            return despachos[p.id] || null;
        }
    },
    ItemPedido: {
        async producto(item, args, ctx) {
            const productos = await lote(ctx, 'productos');
            return productos[item.producto_id] || null;
        }
    },
    ResumenVentas: {
        cantidadVentas: (r) => r.ventas.filter((v) => !v.anulada).length,
        totalVendido: (r) => r.ventas.filter((v) => !v.anulada).reduce((suma, v) => suma + v.total, 0),
        ticketPromedio(r) {
            const validas = r.ventas.filter((v) => !v.anulada);
            return validas.length ? Math.round(validas.reduce((s, v) => s + v.total, 0) / validas.length) : 0;
        },
        ventasAnuladas: (r) => r.ventas.filter((v) => v.anulada).length,
        productos(r) {
            const porNombre = {};
            for (const venta of r.ventas.filter((v) => !v.anulada)) {
                for (const item of venta.items) {
                    porNombre[item.nombre] = porNombre[item.nombre] || { nombre: item.nombre, cantidad: 0, total: 0 };
                    porNombre[item.nombre].cantidad += item.cantidad;
                    porNombre[item.nombre].total += item.subtotal;
                }
            }
            return Object.values(porNombre).sort((a, b) => b.total - a.total);
        },
        // Segundo subsistema (orders). Si orders no responde, el resto del
        // resumen igual se entrega y este campo vuelve con un error parcial.
        async pedidosPorEstado(r, args, ctx) {
            const pedidos = await ctx.llamar('orders', '/interno/pedidos', { desde: r.desde, hasta: r.hasta, limit: 500 });
            const conteo = {};
            for (const p of pedidos) {
                conteo[p.estado] = (conteo[p.estado] || 0) + 1;
            }
            return Object.entries(conteo).map(([estado, cantidad]) => ({ estado, cantidad }));
        }
    }
};

// Limites de profundidad y costo: se revisan antes de ejecutar la consulta
function limitesDeConsulta(context) {
    function medir(selectionSet, profundidad, fragmentosVistos) {
        let campos = 0;
        let maxima = profundidad;
        for (const sel of selectionSet.selections) {
            let resultado = null;
            if (sel.kind === Kind.FIELD) {
                campos += 1;
                if (sel.selectionSet) {
                    resultado = medir(sel.selectionSet, profundidad + 1, fragmentosVistos);
                }
            } else if (sel.kind === Kind.INLINE_FRAGMENT) {
                resultado = medir(sel.selectionSet, profundidad, fragmentosVistos);
            } else if (sel.kind === Kind.FRAGMENT_SPREAD && !fragmentosVistos.has(sel.name.value)) {
                const fragmento = context.getFragment(sel.name.value);
                if (fragmento) {
                    resultado = medir(fragmento.selectionSet, profundidad,
                        new Set([...fragmentosVistos, sel.name.value]));
                }
            }
            if (resultado) {
                campos += resultado.campos;
                maxima = Math.max(maxima, resultado.maxima);
            }
        }
        return { campos, maxima };
    }
    return {
        OperationDefinition(node) {
            const { campos, maxima } = medir(node.selectionSet, 1, new Set());
            if (maxima > PROFUNDIDAD_MAXIMA) {
                context.reportError(new GraphQLError(
                    `La consulta tiene profundidad ${maxima}; el máximo es ${PROFUNDIDAD_MAXIMA}`, [node]));
            }
            if (campos > COSTO_MAXIMO) {
                context.reportError(new GraphQLError(
                    `La consulta pide ${campos} campos; el máximo es ${COSTO_MAXIMO}`, [node]));
            }
        }
    };
}

// Llamada a una API interna con el secreto del tramo graphql-<destino> y plazo maximo
function crearLlamar(salientes, urls = URLS) {
    return async function llamar(destino, ruta, params = {}) {
        const url = new URL(urls[destino] + ruta);
        for (const [clave, valor] of Object.entries(params)) {
            url.searchParams.set(clave, valor);
        }
        let respuesta;
        try {
            respuesta = await fetch(url, {
                headers: { 'X-Service-Name': 'graphql', 'X-Service-Secret': salientes[destino] },
                signal: AbortSignal.timeout(PLAZO_MS)
            });
        } catch (error) {
            throw new ApolloError(`El servicio ${destino} no está disponible`, 'SERVICIO_NO_DISPONIBLE');
        }
        if (!respuesta.ok) {
            throw new ApolloError(`El servicio ${destino} respondió ${respuesta.status}`, 'SERVICIO_NO_DISPONIBLE',
                { status: respuesta.status });
        }
        return respuesta.json();
    };
}

// No se exponen detalles internos en los errores inesperados
function formatearError(error) {
    const codigo = error.extensions && error.extensions.code;
    if (codigo === 'INTERNAL_SERVER_ERROR') {
        return { message: 'Error interno', path: error.path, extensions: { code: codigo } };
    }
    return { message: error.message, path: error.path, extensions: { code: codigo } };
}

function igual(a, b) {
    const x = Buffer.from(a || '');
    const y = Buffer.from(b || '');
    return x.length === y.length && crypto.timingSafeEqual(x, y);
}

async function crearApp({ secretoGateway, llamar }) {
    const app = express();

    // Solo el API Gateway puede llamar al GraphQL Gateway
    app.use('/graphql', (req, res, next) => {
        if (req.get('X-Service-Name') !== 'gateway' || !igual(req.get('X-Service-Secret'), secretoGateway)) {
            return res.status(403).json({ detail: 'Solicitud no autorizada' });
        }
        next();
    });

    app.get('/health', (req, res) => res.json({ status: 'OK', service: 'GraphQL Gateway' }));

    const apolloServer = new ApolloServer({
        typeDefs,
        resolvers,
        introspection: false,
        csrfPrevention: true,
        debug: false,
        validationRules: [limitesDeConsulta],
        formatError: formatearError,
        // Identidad verificada por el API Gateway
        context: ({ req }) => ({
            usuario: {
                user_id: req.get('X-Authenticated-User') || null,
                roles: (req.get('X-Authenticated-Roles') || '').split(',').filter(Boolean)
            },
            llamar,
            lotes: {},
            pedidoIds: [],
            productoIds: []
        })
    });
    await apolloServer.start();
    apolloServer.applyMiddleware({ app, path: '/graphql', cors: false, bodyParserConfig: { limit: '20kb' } });
    return app;
}

async function leerVault(ruta) {
    const respuesta = await fetch(`${VAULT_ADDR}/v1/secret/data/${ruta}`, { headers: { 'X-Vault-Token': VAULT_TOKEN } });
    if (!respuesta.ok) {
        throw new Error(`No fue posible leer ${ruta} desde Vault`);
    }
    return (await respuesta.json()).data.data;
}

async function iniciar() {
    const secretoGateway = (await leerVault('tramos/gateway-graphql')).secret;
    const salientes = {};
    for (const destino of Object.keys(URLS)) {
        salientes[destino] = (await leerVault(`tramos/graphql-${destino}`)).secret;
    }
    const app = await crearApp({ secretoGateway, llamar: crearLlamar(salientes) });
    app.listen(8090, function () {
        console.log('GraphQL Gateway iniciado en el puerto 8090');
    });
}

if (require.main === module) {
    iniciar();
}

module.exports = { crearApp, crearLlamar, limitesDeConsulta, PROFUNDIDAD_MAXIMA, COSTO_MAXIMO };
