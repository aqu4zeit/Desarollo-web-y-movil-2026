// Datos con el mismo formato de respuesta usado en Semana 3 (status, message, data).
const responseCategorias = {
    "status": 200,
    "message": "Categorias obtenidas correctamente",
    "data": [
        { "id": 1, "nombre": "Cafés" },
        { "id": 2, "nombre": "Bebidas frías" },
        { "id": 3, "nombre": "Pastelería" }
    ]
};

const responseProductos = {
    "status": 200,
    "message": "Productos obtenidos correctamente",
    "data": [
        { "id": 1, "categoriaId": 1, "nombre": "Espresso", "descripcion": "Shot intenso de café de especialidad.", "precio": 2200, "destacado": true },
        { "id": 2, "categoriaId": 1, "nombre": "Cappuccino", "descripcion": "Espresso con leche vaporizada y espuma.", "precio": 3200, "destacado": true },
        { "id": 3, "categoriaId": 1, "nombre": "Flat White", "descripcion": "Doble espresso con leche sedosa.", "precio": 3400, "destacado": false },
        { "id": 4, "categoriaId": 1, "nombre": "Filtrado V60", "descripcion": "Método manual que resalta notas del grano.", "precio": 3600, "destacado": false },
        { "id": 5, "categoriaId": 2, "nombre": "Cold Brew", "descripcion": "Café extraído en frío durante 18 horas.", "precio": 3500, "destacado": true },
        { "id": 6, "categoriaId": 2, "nombre": "Latte helado", "descripcion": "Espresso, leche y hielo.", "precio": 3300, "destacado": false },
        { "id": 7, "categoriaId": 3, "nombre": "Croissant", "descripcion": "Hojaldre de mantequilla horneado cada mañana.", "precio": 2500, "destacado": false },
        { "id": 8, "categoriaId": 3, "nombre": "Cheesecake", "descripcion": "Con salsa de frutos rojos.", "precio": 3800, "destacado": false }
    ]
};

const galeria = [
    { "imagen": "https://images.unsplash.com/photo-1760175445000-0e01e193d1cd?w=600&q=80", "titulo": "Nuestro café" },
    { "imagen": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=600&q=80", "titulo": "Nuestro local" },
    { "imagen": "https://images.unsplash.com/photo-1623334044303-241021148842?w=600&q=80", "titulo": "Pastelería" }
];

// Fusion: cada producto se une con el nombre de su categoria.
const productos = responseProductos.data.map((p) => {
    const categoria = responseCategorias.data.find((c) => c.id === p.categoriaId);
    return Object.assign({}, p, { categoria: categoria.nombre });
});

function formatoPrecio(precio) {
    return "$" + precio.toLocaleString("es-CL");
}

// ---- Destacados ----
const listaDestacados = document.getElementById("listaDestacados");

productos.filter((p) => p.destacado).forEach((p) => {
    const item = document.createElement("li");
    item.setAttribute("class", "list-group-item d-flex justify-content-between bg-transparent");

    const nombre = document.createElement("span");
    nombre.innerText = p.nombre;

    const precio = document.createElement("span");
    precio.setAttribute("class", "precio");
    precio.innerText = formatoPrecio(p.precio);

    item.appendChild(nombre);
    item.appendChild(precio);
    listaDestacados.appendChild(item);
});

// ---- Galeria ----
const contenedorGaleria = document.getElementById("contenedorGaleria");

galeria.forEach((foto) => {
    const col = document.createElement("div");
    col.setAttribute("class", "col-md-4");

    const caja = document.createElement("figure");
    caja.setAttribute("class", "foto");

    const imagen = document.createElement("img");
    imagen.setAttribute("src", foto.imagen);
    imagen.setAttribute("alt", foto.titulo);

    const titulo = document.createElement("figcaption");
    titulo.innerText = foto.titulo;

    caja.appendChild(imagen);
    caja.appendChild(titulo);
    col.appendChild(caja);
    contenedorGaleria.appendChild(col);
});

// ---- Menu con filtro por categoria ----
const cmbCategoria = document.getElementById("cmbCategoria");
const contenedorMenu = document.getElementById("contenedorMenu");

responseCategorias.data.forEach((c) => {
    const opt = document.createElement("option");
    opt.setAttribute("value", c.id);
    opt.innerText = c.nombre;
    cmbCategoria.appendChild(opt);
});

function mostrarMenu(lista) {
    contenedorMenu.innerHTML = "";

    lista.forEach((p) => {
        const col = document.createElement("div");
        col.setAttribute("class", "col-sm-6 col-lg-3");

        const card = document.createElement("div");
        card.setAttribute("class", "card card-menu h-100");

        const cardBody = document.createElement("div");
        cardBody.setAttribute("class", "card-body");

        const categoria = document.createElement("small");
        categoria.setAttribute("class", "text-uppercase");
        categoria.innerText = p.categoria;

        const titulo = document.createElement("h5");
        titulo.setAttribute("class", "card-title mt-1");
        titulo.innerText = p.nombre;

        const descripcion = document.createElement("p");
        descripcion.setAttribute("class", "card-text");
        descripcion.innerText = p.descripcion;

        const precio = document.createElement("p");
        precio.setAttribute("class", "precio mb-0");
        precio.innerText = formatoPrecio(p.precio);

        cardBody.appendChild(categoria);
        cardBody.appendChild(titulo);
        cardBody.appendChild(descripcion);
        cardBody.appendChild(precio);
        card.appendChild(cardBody);
        col.appendChild(card);
        contenedorMenu.appendChild(col);
    });
}

cmbCategoria.addEventListener("change", () => {
    if (cmbCategoria.value === "") {
        mostrarMenu(productos);
        return;
    }
    mostrarMenu(productos.filter((p) => p.categoriaId === Number(cmbCategoria.value)));
});

mostrarMenu(productos);

// ---- Promociones ----
const suscriptores = [];
const txtCorreoPromo = document.getElementById("txtCorreoPromo");
const msgPromo = document.getElementById("msgPromo");

function correoValido(correo) {
    return correo.includes("@") && correo.includes(".");
}

document.getElementById("btnSuscribir").addEventListener("click", () => {
    const correo = txtCorreoPromo.value.trim();

    if (!correoValido(correo)) {
        msgPromo.innerText = "Ingresa un correo válido.";
        return;
    }
    if (suscriptores.includes(correo)) {
        msgPromo.innerText = "Ese correo ya está suscrito.";
        return;
    }

    suscriptores.push(correo);
    console.log("Suscriptores:", suscriptores);
    msgPromo.innerText = "¡Listo! Te enviaremos nuestras promociones.";
    txtCorreoPromo.value = "";
});

// ---- Contacto ----
const mensajes = [];
const msgContacto = document.getElementById("msgContacto");

function mostrarAlerta(tipo, texto) {
    msgContacto.innerHTML = "";
    const alerta = document.createElement("div");
    alerta.setAttribute("class", "alert alert-" + tipo);
    alerta.innerText = texto;
    msgContacto.appendChild(alerta);
}

document.getElementById("btnEnviar").addEventListener("click", () => {
    const nombre = document.getElementById("txtNombre").value.trim();
    const correo = document.getElementById("txtCorreo").value.trim();
    const mensaje = document.getElementById("txtMensaje").value.trim();

    if (!nombre || !correo || !mensaje) {
        mostrarAlerta("warning", "Debes completar todos los campos.");
        return;
    }
    if (!correoValido(correo)) {
        mostrarAlerta("warning", "Ingresa un correo válido.");
        return;
    }

    mensajes.push({ nombre, correo, mensaje });
    console.log("Mensajes:", mensajes);
    mostrarAlerta("success", `Gracias ${nombre}, responderemos a la brevedad.`);

    document.getElementById("txtNombre").value = "";
    document.getElementById("txtCorreo").value = "";
    document.getElementById("txtMensaje").value = "";
});
