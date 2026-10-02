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
        { "id": 1, "categoriaId": 1, "nombre": "Espresso", "descripcion": "Shot intenso de café de especialidad.", "precio": 2200, "destacado": true, "imagen": "https://images.unsplash.com/photo-1705952285570-113e76f63fb0?w=120&h=120&fit=crop&q=80" },
        { "id": 2, "categoriaId": 1, "nombre": "Cappuccino", "descripcion": "Espresso con leche vaporizada y espuma.", "precio": 3200, "destacado": true, "imagen": "https://images.unsplash.com/photo-1572442388796-11668a67e53d?w=120&h=120&fit=crop&q=80" },
        { "id": 3, "categoriaId": 1, "nombre": "Flat White", "descripcion": "Doble espresso con leche sedosa.", "precio": 3400, "destacado": false },
        { "id": 4, "categoriaId": 1, "nombre": "Filtrado V60", "descripcion": "Método manual que resalta notas del grano.", "precio": 3600, "destacado": false },
        { "id": 5, "categoriaId": 2, "nombre": "Cold Brew", "descripcion": "Café extraído en frío durante 18 horas.", "precio": 3500, "destacado": true, "imagen": "https://images.unsplash.com/photo-1625126590447-cb769384e1f0?w=120&h=120&fit=crop&q=80" },
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

// Cambia el contenido de una caja y anima su alto del valor anterior al nuevo,
// para que crezca o se achique sin salto. Tecnica de CSS-Tricks "Using CSS
// Transitions on Auto Dimensions": medir antes, cambiar, medir despues y animar.
function animarAlto(elemento, cambiarContenido) {
    const altoAntes = elemento.offsetHeight;
    cambiarContenido();
    const altoDespues = elemento.offsetHeight;

    if (altoAntes === altoDespues || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        return;
    }

    elemento.style.overflow = "hidden";
    const animacion = elemento.animate(
        [{ height: altoAntes + "px" }, { height: altoDespues + "px" }],
        { duration: 400, easing: "ease" }
    );
    animacion.onfinish = () => {
        elemento.style.overflow = "";
    };
}

// ---- Destacados ----
const listaDestacados = document.getElementById("listaDestacados");

// Cada destacado entra con AOS, uno tras otro (150 ms de diferencia)
productos.filter((p) => p.destacado).forEach((p, indice) => {
    const item = document.createElement("li");
    item.setAttribute("class", "list-group-item d-flex align-items-center gap-3 bg-transparent");
    item.setAttribute("data-aos", "fade-up");
    item.setAttribute("data-aos-delay", indice * 150);

    const miniatura = document.createElement("img");
    miniatura.setAttribute("class", "miniatura");
    miniatura.setAttribute("src", p.imagen);
    miniatura.setAttribute("alt", p.nombre);

    const nombre = document.createElement("span");
    nombre.setAttribute("class", "flex-grow-1");
    nombre.innerText = p.nombre;

    const precio = document.createElement("span");
    precio.setAttribute("class", "precio");
    precio.innerText = formatoPrecio(p.precio);

    item.appendChild(miniatura);
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
// Un boton por categoria (antes era un select); filtra igual que antes.
const filtroCategorias = document.getElementById("filtroCategorias");
const contenedorMenu = document.getElementById("contenedorMenu");

function crearBotonCategoria(texto, valor) {
    const btn = document.createElement("button");
    btn.setAttribute("type", "button");
    btn.setAttribute("class", "btn btn-categoria");
    btn.innerText = texto;

    btn.addEventListener("click", () => {
        filtroCategorias.querySelectorAll(".btn-categoria").forEach((b) => {
            b.classList.remove("active");
        });
        btn.classList.add("active");

        // Al filtrar, la caja del menu cambia de alto de forma suave
        animarAlto(contenedorMenu, () => {
            if (valor === "") {
                mostrarMenu(productos);
                return;
            }
            mostrarMenu(productos.filter((p) => p.categoriaId === valor));
        });
    });

    filtroCategorias.appendChild(btn);
    return btn;
}

crearBotonCategoria("Todas", "").classList.add("active");
responseCategorias.data.forEach((c) => {
    crearBotonCategoria(c.nombre, c.id);
});

// La columna lleva la animacion de entrada (AOS) y la tarjeta el efecto
// al pasar el mouse (Hover.css), porque los dos usan transform.
function mostrarMenu(lista) {
    contenedorMenu.innerHTML = "";

    lista.forEach((p, indice) => {
        const col = document.createElement("div");
        col.setAttribute("class", "col-sm-6 col-lg-3");
        col.setAttribute("data-aos", "zoom-in");
        // AOS solo trae retrasos en multiplos de 50 ms
        col.setAttribute("data-aos-delay", indice * 100);

        const card = document.createElement("div");
        card.setAttribute("class", "card card-menu h-100 hvr-float");

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

mostrarMenu(productos);

// ---- Promociones ----
const suscriptores = [];
const txtCorreoPromo = document.getElementById("txtCorreoPromo");
const msgPromo = document.getElementById("msgPromo");

// El mensaje aparece y la caja crece de forma suave
function mostrarMsgPromo(texto) {
    animarAlto(msgPromo, () => {
        msgPromo.innerText = texto;
    });
}

function correoValido(correo) {
    return correo.includes("@") && correo.includes(".");
}

document.getElementById("btnSuscribir").addEventListener("click", () => {
    const correo = txtCorreoPromo.value.trim();

    if (!correoValido(correo)) {
        mostrarMsgPromo("Ingresa un correo válido.");
        return;
    }
    if (suscriptores.includes(correo)) {
        mostrarMsgPromo("Ese correo ya está suscrito.");
        return;
    }

    suscriptores.push(correo);
    console.log("Suscriptores:", suscriptores);
    mostrarMsgPromo("¡Listo! Te enviaremos nuestras promociones.");
    txtCorreoPromo.value = "";
});

// ---- Contacto ----
const mensajes = [];
const msgContacto = document.getElementById("msgContacto");

function mostrarAlerta(tipo, texto) {
    animarAlto(msgContacto, () => {
        msgContacto.innerHTML = "";
        const alerta = document.createElement("div");
        alerta.setAttribute("class", "alert alert-" + tipo);
        alerta.innerText = texto;
        msgContacto.appendChild(alerta);
    });
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

// ---- Barra lateral ----
const sidebar = document.getElementById("sidebar");
const btnColapsar = document.getElementById("btnColapsar");

btnColapsar.addEventListener("click", () => {
    sidebar.classList.toggle("colapsada");
    if (sidebar.classList.contains("colapsada")) {
        btnColapsar.setAttribute("title", "Abrir barra");
    } else {
        btnColapsar.setAttribute("title", "Cerrar barra");
    }
});

// Marca la seccion que se esta viendo (Gumshoe): la activa es la ultima
// cuyo borde superior paso la mitad de la pantalla
const spy = new Gumshoe("#navSecciones a", {
    offset: () => window.innerHeight / 2
});

// Al elegir una seccion se centra en la pantalla, asi queda marcada como la actual.
// Si es mas alta que la pantalla (el menu) se alinea arriba para que se vea su titulo.
// En celular ademas se cierra el panel.
document.querySelectorAll("#sidebar .nav-link").forEach((link) => {
    link.addEventListener("click", (e) => {
        e.preventDefault();
        const seccion = document.querySelector(link.getAttribute("href"));
        let posicion = "center";
        if (seccion.offsetHeight > window.innerHeight) {
            posicion = "start";
        }
        seccion.scrollIntoView({ behavior: "smooth", block: posicion });

        const panel = bootstrap.Offcanvas.getInstance(sidebar);
        if (panel) {
            panel.hide();
        }
    });
});

// ---- Rebote al llegar al final de la pagina ----
// Al seguir girando la rueda en el final, el contenido se estira hacia arriba
// con resistencia y al soltar vuelve a su lugar. Ninguna libreria lo hace con el
// scroll normal de la ventana en escritorio sin reemplazarlo, asi que se usa la
// formula de "rubber band" de iOS: (1 - 1 / (distancia * c / limite + 1)) * limite
const contenido = document.querySelector(".contenido");
const limiteRebote = 120;
let distanciaEstirada = 0;
let temporizadorRebote;

function alFinalDeLaPagina() {
    return window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 1;
}

function estirar(distancia) {
    distanciaEstirada = distanciaEstirada + distancia;
    const desplazamiento = (1 - 1 / (distanciaEstirada * 0.55 / limiteRebote + 1)) * limiteRebote;
    contenido.style.transition = "none";
    contenido.style.transform = "translateY(" + (-desplazamiento) + "px)";
}

function soltar() {
    distanciaEstirada = 0;
    contenido.style.transition = "transform 0.5s cubic-bezier(0.25, 1.4, 0.5, 1)";
    contenido.style.transform = "";
}

window.addEventListener("wheel", (e) => {
    if (e.deltaY <= 0 || !alFinalDeLaPagina() || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        return;
    }
    estirar(e.deltaY);
    clearTimeout(temporizadorRebote);
    temporizadorRebote = setTimeout(soltar, 150);
}, { passive: true });

// ---- Animaciones al hacer scroll (AOS) ----
// Va al final para que ya existan los elementos creados arriba con JavaScript.
// once: cada elemento se anima solo la primera vez que aparece.
AOS.init({
    once: true,
    duration: 600
});
