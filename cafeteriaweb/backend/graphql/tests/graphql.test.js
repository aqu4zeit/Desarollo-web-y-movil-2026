const { test, before, after } = require('node:test');
const assert = require('node:assert');
const { ApolloError } = require('apollo-server-express');
const { buildSchema, parse, validate } = require('graphql');
const { crearApp, limitesDeConsulta } = require('../server');

const SECRETO = 's-gateway';

const PEDIDOS = [
    {
        id: 'PED-1', user_id: 'USR-0005', estado: 'pagado', total: 6900, creado: '2026-10-21T19:42:22Z',
        motivo_anulacion: null, historial: [{ estado: 'pendiente_pago', fecha: '2026-10-21T19:40:00Z' }],
        cliente: { nombre: 'Camila', direccion: 'San Diego 850', comuna: 'Santiago', telefono: '+56911111111' },
        items: [{ producto_id: 'p1', nombre: 'Espresso', precio: 2200, cantidad: 2, subtotal: 4400 },
            { producto_id: 'p2', nombre: 'Croissant', precio: 2500, cantidad: 1, subtotal: 2500 }]
    },
    {
        id: 'PED-2', user_id: 'USR-0005', estado: 'anulado', total: 3800, creado: '2026-10-21T20:00:00Z',
        motivo_anulacion: 'Me equivoqué', historial: [],
        cliente: { nombre: 'Camila', direccion: 'San Diego 850', comuna: 'Santiago', telefono: '+56911111111' },
        items: [{ producto_id: 'p1', nombre: 'Espresso', precio: 2200, cantidad: 1, subtotal: 2200 }]
    }
];

const VENTAS = [
    { total: 6900, anulada: false, items: PEDIDOS[0].items },
    { total: 3800, anulada: true, items: [{ nombre: 'Cheesecake', cantidad: 1, subtotal: 3800 }] }
];

// Servicios internos falsos: registra cada llamada para comprobar el batching
const estado = { llamadas: [], caidos: new Set() };

async function llamar(destino, ruta, params = {}) {
    estado.llamadas.push(`${destino} ${ruta}`);
    if (estado.caidos.has(destino)) {
        throw new ApolloError(`El servicio ${destino} no está disponible`, 'SERVICIO_NO_DISPONIBLE');
    }
    if (destino === 'orders' && ruta === '/interno/pedidos') {
        return params.user_id ? PEDIDOS.filter((p) => p.user_id === params.user_id) : PEDIDOS;
    }
    if (destino === 'orders') {
        const pedido = PEDIDOS.find((p) => ruta.endsWith(p.id));
        if (!pedido) {
            throw new ApolloError('no encontrado', 'SERVICIO_NO_DISPONIBLE', { status: 404 });
        }
        return pedido;
    }
    if (destino === 'payments' && ruta === '/interno/pagos') {
        return { 'PED-1': { id: 'PAG-1', estado: 'aprobado', monto: 6900, folio_boleta: 1 } };
    }
    if (destino === 'payments' && ruta === '/ventas') {
        return VENTAS;
    }
    if (destino === 'despacho') {
        return { 'PED-1': { numero: 1, estado: 'pendiente', chofer: null } };
    }
    if (destino === 'inventory') {
        estado.idsInventory = params.ids;
        return [{ id: 'p1', nombre: 'Espresso', precio: 2200, imagen: null, disponible: true },
            { id: 'p2', nombre: 'Croissant', precio: 2500, imagen: null, disponible: false }];
    }
    throw new Error(`llamada inesperada ${destino} ${ruta}`);
}

let servidor;
let url;

before(async () => {
    const app = await crearApp({ secretoGateway: SECRETO, llamar });
    servidor = app.listen(0);
    url = `http://127.0.0.1:${servidor.address().port}/graphql`;
});

after(() => servidor.close());

async function consultar(query, { user = 'USR-0005', roles = 'cliente', secreto = SECRETO } = {}) {
    estado.llamadas = [];
    const headers = { 'Content-Type': 'application/json', 'X-Service-Name': 'gateway', 'X-Service-Secret': secreto };
    if (user) {
        headers['X-Authenticated-User'] = user;
        headers['X-Authenticated-Roles'] = roles;
    }
    const r = await fetch(url, { method: 'POST', headers, body: JSON.stringify({ query }) });
    return { status: r.status, cuerpo: r.status === 403 ? null : await r.json() };
}

const MIS_PEDIDOS = `{ misPedidos { id estado total items { nombre producto { disponible } }
    pago { estado folioBoleta } despacho { numero estado } } }`;

test('mis pedidos combina orders, payments, despacho e inventory', async () => {
    const { cuerpo } = await consultar(MIS_PEDIDOS);
    assert.strictEqual(cuerpo.errors, undefined);
    const [p1, p2] = cuerpo.data.misPedidos;
    assert.strictEqual(p1.pago.folioBoleta, 1);
    assert.strictEqual(p1.despacho.numero, 1);
    assert.strictEqual(p1.items[1].producto.disponible, false);
    assert.strictEqual(p2.pago, null);
});

test('batching: una llamada por servicio aunque haya varios pedidos e items', async () => {
    await consultar(MIS_PEDIDOS);
    assert.deepStrictEqual(estado.llamadas.sort(), [
        'despacho /interno/ordenes', 'inventory /productos', 'orders /interno/pedidos', 'payments /interno/pagos'
    ]);
});

test('sin el secreto del API Gateway se rechaza', async () => {
    assert.strictEqual((await consultar(MIS_PEDIDOS, { secreto: 'otro' })).status, 403);
});

test('sin sesión o con otro rol no hay pedidos', async () => {
    const sinSesion = await consultar(MIS_PEDIDOS, { user: null });
    assert.strictEqual(sinSesion.cuerpo.errors[0].extensions.code, 'UNAUTHENTICATED');
    const otroRol = await consultar(MIS_PEDIDOS, { user: 'USR-0002', roles: 'dueno' });
    assert.strictEqual(otroRol.cuerpo.errors[0].extensions.code, 'FORBIDDEN');
});

test('autorización por recurso: un pedido ajeno vuelve null', async () => {
    const { cuerpo } = await consultar('{ pedido(id: "PED-1") { id } }', { user: 'USR-0006' });
    assert.strictEqual(cuerpo.data.pedido, null);
});

test('autorización por campo: el dueño no ve los datos del cliente', async () => {
    const { cuerpo } = await consultar('{ pedido(id: "PED-1") { id total cliente { nombre telefono } } }',
        { user: 'USR-0002', roles: 'dueno' });
    assert.strictEqual(cuerpo.data.pedido.total, 6900);
    assert.strictEqual(cuerpo.data.pedido.cliente, null);
    assert.strictEqual(cuerpo.errors[0].extensions.code, 'FORBIDDEN');
});

test('error parcial: si payments está caído el resto del pedido llega igual', async () => {
    estado.caidos.add('payments');
    const { cuerpo } = await consultar('{ pedido(id: "PED-1") { id estado pago { estado } despacho { numero } } }');
    estado.caidos.delete('payments');
    assert.strictEqual(cuerpo.data.pedido.estado, 'pagado');
    assert.strictEqual(cuerpo.data.pedido.pago, null);
    assert.strictEqual(cuerpo.data.pedido.despacho.numero, 1);
    assert.deepStrictEqual(cuerpo.errors[0].path, ['pedido', 'pago']);
});

test('resumen de ventas combina payments y orders, solo dueño o admin', async () => {
    const q = `{ resumenVentas(desde: "2026-10-01", hasta: "2026-10-31") {
        cantidadVentas totalVendido ticketPromedio ventasAnuladas productos { nombre cantidad } pedidosPorEstado { estado cantidad } } }`;
    const { cuerpo } = await consultar(q, { user: 'USR-0002', roles: 'dueno' });
    const r = cuerpo.data.resumenVentas;
    assert.strictEqual(r.cantidadVentas, 1);
    assert.strictEqual(r.totalVendido, 6900);
    assert.strictEqual(r.ventasAnuladas, 1);
    assert.strictEqual(r.productos[0].nombre, 'Espresso');
    assert.strictEqual(r.pedidosPorEstado.length, 2);
    const cliente = await consultar(q);
    assert.strictEqual(cliente.cuerpo.errors[0].extensions.code, 'FORBIDDEN');
});

test('resumen con orders caído: error parcial solo en pedidosPorEstado', async () => {
    estado.caidos.add('orders');
    const { cuerpo } = await consultar('{ resumenVentas(desde: "2026-10-01", hasta: "2026-10-31") { totalVendido pedidosPorEstado { estado } } }',
        { user: 'USR-0001', roles: 'admin' });
    estado.caidos.delete('orders');
    assert.strictEqual(cuerpo.data.resumenVentas.totalVendido, 6900);
    assert.strictEqual(cuerpo.data.resumenVentas.pedidosPorEstado, null);
});

test('paginación limitada', async () => {
    const { cuerpo } = await consultar('{ misPedidos(primeros: 500) { id } }');
    assert.strictEqual(cuerpo.errors[0].extensions.code, 'BAD_USER_INPUT');
});

test('límite de costo: demasiados campos con alias', async () => {
    const alias = Array.from({ length: 40 }, (_, i) => `a${i}: misPedidos { id estado total }`).join(' ');
    const { status, cuerpo } = await consultar(`{ ${alias} }`);
    assert.strictEqual(status, 400);
    assert.match(cuerpo.errors[0].message, /máximo es 150/);
});

test('límite de profundidad (regla aplicada a un esquema recursivo)', () => {
    // El esquema de Aroma no es recursivo; se prueba la regla con uno que si lo es
    const schema = buildSchema('type Query { nodo: Nodo } type Nodo { hijo: Nodo, valor: Int }');
    const ok = parse('{ nodo { hijo { hijo { valor } } } }');
    const profunda = parse('{ nodo { hijo { hijo { hijo { hijo { hijo { hijo { valor } } } } } } } }');
    assert.strictEqual(validate(schema, ok, [limitesDeConsulta]).length, 0);
    assert.match(validate(schema, profunda, [limitesDeConsulta])[0].message, /profundidad 8/);
});

test('introspección deshabilitada', async () => {
    const { cuerpo } = await consultar('{ __schema { types { name } } }');
    assert.ok(cuerpo.errors.length > 0);
});
