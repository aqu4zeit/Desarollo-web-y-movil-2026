// ---- Conexion con el backend ----
const API_URL = "http://localhost:8000";

// Devuelve {status, message, data}; status 0 si el gateway no responde
async function llamarApi(metodo, ruta, cuerpo) {
    const opciones = { method: metodo, credentials: "include", headers: {} };
    if (cuerpo !== undefined) {
        opciones.headers["Content-Type"] = "application/json";
        opciones.body = JSON.stringify(cuerpo);
    }

    let respuesta;
    try {
        respuesta = await fetch(API_URL + ruta, opciones);
    } catch (error) {
        console.log(metodo, ruta, "-> sin respuesta del gateway");
        return { status: 0, message: "Sin conexión con el servidor", data: null };
    }

    const correlacion = respuesta.headers.get("X-Correlation-Id");
    console.log(metodo, ruta, "->", respuesta.status, "correlacion:", correlacion);

    let data = null;
    try {
        data = await respuesta.json();
    } catch (error) {
        data = null;
    }
    let message = "";
    if (data && data.message) {
        message = data.message;
    } else if (data && typeof data.detail === "string") {
        message = data.detail;
    }
    return { status: respuesta.status, message: message, data: data };
}

const galeria = [
    { "imagen": "https://images.unsplash.com/photo-1760175445000-0e01e193d1cd?w=600&q=80", "titulo": "Nuestro café" },
    { "imagen": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=600&q=80", "titulo": "Nuestro local" },
    { "imagen": "https://images.unsplash.com/photo-1623334044303-241021148842?w=600&q=80", "titulo": "Pastelería" }
];

// Productos del catalogo con el nombre de su categoria
let productos = [];

function formatoPrecio(precio) {
    return "$" + precio.toLocaleString("es-CL");
}

// Anima el alto de una caja cuando cambia su contenido
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
function mostrarDestacados() {
    listaDestacados.innerHTML = "";
    const destacados = productos.filter((p) => p.destacado);

    if (destacados.length === 0) {
        mostrarAviso(listaDestacados, "li", "No hay destacados por ahora.", false);
        return;
    }

    destacados.forEach((p, indice) => {
        const item = document.createElement("li");
        item.setAttribute("class", "list-group-item d-flex align-items-center gap-3 bg-transparent");
        item.setAttribute("data-aos", "fade-up");
        item.setAttribute("data-aos-delay", indice * 150);

        // Puede venir sin imagen
        if (p.imagen) {
            const miniatura = document.createElement("img");
            miniatura.setAttribute("class", "miniatura");
            miniatura.setAttribute("src", p.imagen);
            miniatura.setAttribute("alt", p.nombre);
            item.appendChild(miniatura);
        }

        const nombre = document.createElement("span");
        nombre.setAttribute("class", "flex-grow-1");
        nombre.innerText = p.nombre;

        const precio = document.createElement("span");
        precio.setAttribute("class", "precio");
        precio.innerText = formatoPrecio(p.precio);

        item.appendChild(nombre);
        item.appendChild(precio);
        listaDestacados.appendChild(item);
    });
}

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
// Un boton por categoria
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
            mostrarMenu(productos.filter((p) => p.categoria_id === valor));
        });
    });

    filtroCategorias.appendChild(btn);
    return btn;
}

function crearFiltros(categorias) {
    filtroCategorias.innerHTML = "";
    crearBotonCategoria("Todas", "").classList.add("active");
    categorias.forEach((c) => {
        crearBotonCategoria(c.nombre, c.id);
    });
}

// Columna con AOS y tarjeta con Hover.css
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

        // disponible = activo y con stock
        if (!p.disponible) {
            card.classList.add("agotado");
            const etiqueta = document.createElement("span");
            etiqueta.setAttribute("class", "badge etiqueta-agotado mt-2");
            etiqueta.innerText = "Agotado";
            cardBody.appendChild(etiqueta);
        }
        card.appendChild(cardBody);
        col.appendChild(card);
        contenedorMenu.appendChild(col);
    });
}

// ---- Carga del catalogo ----
// Aviso de cargando, sin productos o no disponible
function mostrarAviso(contenedor, etiqueta, texto, conReintento) {
    const aviso = document.createElement(etiqueta);
    if (etiqueta === "li") {
        aviso.setAttribute("class", "list-group-item bg-transparent aviso-catalogo");
    } else {
        aviso.setAttribute("class", "col-12 aviso-catalogo");
    }

    const parrafo = document.createElement("p");
    parrafo.setAttribute("class", "mb-2");
    parrafo.innerText = texto;
    aviso.appendChild(parrafo);

    if (conReintento) {
        const btn = document.createElement("button");
        btn.setAttribute("type", "button");
        btn.setAttribute("class", "btn btn-cafe btn-sm");
        btn.innerText = "Reintentar";
        btn.addEventListener("click", cargarCatalogo);
        aviso.appendChild(btn);
    }
    contenedor.appendChild(aviso);
}

async function cargarCatalogo() {
    listaDestacados.innerHTML = "";
    contenedorMenu.innerHTML = "";
    filtroCategorias.innerHTML = "";
    mostrarAviso(listaDestacados, "li", "Cargando destacados...", false);
    mostrarAviso(contenedorMenu, "div", "Cargando el menú...", false);

    // Las dos consultas se hacen al mismo tiempo
    const respuestas = await Promise.all([
        llamarApi("GET", "/api/categorias"),
        llamarApi("GET", "/api/productos")
    ]);
    const responseCategorias = respuestas[0];
    const responseProductos = respuestas[1];

    // Si falla cualquiera de las dos no se muestra un menu a medias
    if (responseCategorias.status !== 200 || responseProductos.status !== 200) {
        productos = [];
        listaDestacados.innerHTML = "";
        contenedorMenu.innerHTML = "";
        mostrarAviso(listaDestacados, "li", "Los destacados no están disponibles en este momento.", false);
        mostrarAviso(contenedorMenu, "div", "El menú no está disponible en este momento. Intenta de nuevo en unos minutos.", true);
        return;
    }

    // Une cada producto con el nombre de su categoria
    productos = responseProductos.data.map((p) => {
        const categoria = responseCategorias.data.find((c) => c.id === p.categoria_id);
        let nombreCategoria = "";
        if (categoria) {
            nombreCategoria = categoria.nombre;
        }
        return Object.assign({}, p, { categoria: nombreCategoria });
    });

    mostrarDestacados();
    crearFiltros(responseCategorias.data);
    if (productos.length === 0) {
        contenedorMenu.innerHTML = "";
        mostrarAviso(contenedorMenu, "div", "Todavía no hay productos en el menú.", false);
        return;
    }
    mostrarMenu(productos);
}

cargarCatalogo();

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

// Misma regla de correo que el backend
function correoValido(correo) {
    return /^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$/.test(correo);
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
const msgContacto = document.getElementById("msgContacto");
const btnEnviar = document.getElementById("btnEnviar");

// Campos que puede rechazar el backend (422)
const camposContacto = { "nombre": "nombre", "correo": "correo", "mensaje": "mensaje" };

function mostrarAlerta(tipo, texto) {
    animarAlto(msgContacto, () => {
        msgContacto.innerHTML = "";
        const alerta = document.createElement("div");
        alerta.setAttribute("class", "alert alert-" + tipo);
        alerta.innerText = texto;
        msgContacto.appendChild(alerta);
    });
}

// Mismas reglas que el backend
function validarContacto(nombre, correo, mensaje) {
    if (!nombre || !correo || !mensaje) {
        return "Debes completar todos los campos.";
    }
    if (nombre.length < 3) {
        return "El nombre debe tener al menos 3 caracteres.";
    }
    if (!correoValido(correo)) {
        return "Ingresa un correo válido.";
    }
    if (mensaje.length < 5) {
        return "El mensaje debe tener al menos 5 caracteres.";
    }
    return "";
}

btnEnviar.addEventListener("click", async () => {
    const nombre = document.getElementById("txtNombre").value.trim();
    const correo = document.getElementById("txtCorreo").value.trim();
    const mensaje = document.getElementById("txtMensaje").value.trim();

    const error = validarContacto(nombre, correo, mensaje);
    if (error) {
        mostrarAlerta("warning", error);
        return;
    }

    // Desactivado para no enviar dos veces
    btnEnviar.disabled = true;
    btnEnviar.innerText = "Enviando...";
    const respuesta = await llamarApi("POST", "/api/contacto", { nombre, correo, mensaje });
    btnEnviar.disabled = false;
    btnEnviar.innerText = "Enviar";

    if (respuesta.status === 201) {
        mostrarAlerta("success", `Gracias ${nombre}. ${respuesta.message}`);
        document.getElementById("txtNombre").value = "";
        document.getElementById("txtCorreo").value = "";
        document.getElementById("txtMensaje").value = "";
        return;
    }

    // En los errores se conserva lo escrito
    if (respuesta.status === 422) {
        let campos = [];
        if (Array.isArray(respuesta.data.detail)) {
            campos = respuesta.data.detail.map((d) => camposContacto[d.loc[d.loc.length - 1]]).filter((c) => c);
        }
        let texto = "El servidor rechazó los datos. Revisa el formulario.";
        if (campos.length > 0) {
            texto = "El servidor rechazó los datos. Revisa: " + campos.join(", ") + ".";
        }
        mostrarAlerta("warning", texto);
        return;
    }
    if (respuesta.status === 429) {
        mostrarAlerta("warning", "Enviaste demasiadas solicitudes. Espera un minuto e intenta de nuevo.");
        return;
    }
    if (respuesta.status === 0) {
        mostrarAlerta("danger", "No pudimos conectar con el servidor. Revisa tu conexión e intenta de nuevo.");
        return;
    }
    mostrarAlerta("danger", "El servicio de mensajes no está disponible en este momento. Intenta de nuevo en unos minutos.");
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

// Marca la seccion visible (Gumshoe)
const spy = new Gumshoe("#navSecciones a", {
    offset: () => window.innerHeight / 2
});

// Centra la seccion elegida y en celular cierra el panel
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
// Formula de rubber band de iOS
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
// Va al final para animar tambien lo creado con JavaScript
AOS.init({
    once: true,
    duration: 600
});
