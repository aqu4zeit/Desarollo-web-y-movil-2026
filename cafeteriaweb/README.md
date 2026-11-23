# Aroma & Café

Página web y backend de la cafetería Aroma & Café, proyecto del ramo Desarrollo Web y Móvil (NRC 8481, UNAB).
Caso 4 del curso: café de especialidad y repostería.

Página publicada: https://aqu4zeit.github.io/Desarollo-web-y-movil-2026/cafeteriaweb/

## Estructura

```
cafeteriaweb/
├── index.html      # página de inicio con todas las secciones
├── mi-cuenta.html  # Mi cuenta del cliente (P08, incremento 7: archivo creado, pendiente)
├── panel.html      # panel del personal (P09, incremento 8: archivo creado, pendiente)
├── favicon.svg     # ícono de la pestaña (taza con la paleta de la página)
├── css/
│   └── estilos.css # paleta (Propuesta 1, Semana 4) y estilos
├── js/
│   ├── app.js       # conexión con el gateway, menú, filtro, formularios y animaciones
│   ├── mi-cuenta.js # lógica de mi-cuenta.html (pendiente)
│   └── panel.js     # lógica de panel.html (pendiente)
├── pruebas/        # criterios de aceptación de cada flujo en Gherkin (F00 a F08)
└── backend/        # microservicios, gateways y Docker (ver backend/README.md)
```

## Cómo verla en local

La página lee el menú y guarda los mensajes de contacto en el backend, así que primero hay que levantarlo
(ver la sección Backend). Después, en la carpeta `cafeteriaweb`:

```
py -m http.server 5500
```

y entrar a **http://localhost:5500**. Usar `localhost` y no `127.0.0.1`: el gateway solo autoriza (CORS) el origen
`http://localhost:5500`. Abrir `index.html` con doble clic tampoco funciona, porque el navegador no deja que una
página `file://` llame a la API.

## Backend

El backend (Evaluación 2) se levanta desde `backend/` con `.\preparar.ps1` y responde en http://localhost:8000/api.
Las instrucciones, los usuarios de prueba y las pruebas están en [backend/README.md](backend/README.md).

## Integración (Evaluación 3)

La página se conecta con el backend de a un flujo por vez. Cada flujo tiene sus escenarios en `pruebas/`.

| Flujo | Qué hace la página | Servicios | Estado |
|---|---|---|---|
| F00 Entorno | El gateway autoriza (CORS) a `http://localhost:5500` y expone el id de correlación | API Gateway | Integrado |
| F01 Menú y destacados | Lee categorías y productos; muestra "Agotado", "cargando" y "no disponible" con botón Reintentar | API Gateway, inventory | Integrado |
| F02 Contacto | Valida igual que el backend y guarda el mensaje; conserva lo escrito si el servicio falla | API Gateway, clients | Integrado |
| F03 en adelante | Cuenta, sesión, promociones, pedido y pago, Mi cuenta, panel del personal | — | Pendiente |

Cada solicitud de la página escribe en la consola del navegador la ruta, el código HTTP y el id de correlación; el
mismo id aparece en el log del gateway (`docker compose logs gateway`).

La versión publicada en GitHub Pages no alcanza el backend local, así que ahí el menú muestra el aviso de "no
disponible". La integración se prueba en local.

## Librerías (por CDN)

| Librería | Para qué se usa | Licencia |
|---|---|---|
| [Bootstrap 5.3.8](https://getbootstrap.com) | Grilla, botones, modal, menú del celular y formulario | MIT |
| [Font Awesome 4.7](https://fontawesome.com/v4/) | Íconos | SIL OFL / MIT |
| [Google Fonts](https://fonts.google.com) | Playfair Display (títulos) y Lato (texto) | SIL OFL |
| [Animate.css 4.1.1](https://animate.style) | Animaciones al cargar la página y en el modal | MIT |
| [AOS 2.3.4](https://michalsnik.github.io/aos/) | Animaciones al hacer scroll | MIT |
| [Hover.css 2.3.1](https://ianlunn.github.io/Hover/) | Tarjetas del menú que suben al pasar el mouse | MIT |
| [Gumshoe 5.1.1](https://github.com/cferdinandi/gumshoe) | Marca en la barra la sección que se está viendo | MIT |

## Qué se hizo y de dónde salió

### Barra lateral
- **Se minimiza** con la flecha y queda con el monograma "A&C", los íconos y las redes. Basada en [Collapsible Sidebar with Icons](https://codepen.io/codepen-the-selector/pen/GRVJdyg) (CodePen).
- **Transición suave:** los íconos no se mueven, el texto se desvanece y las redes se deslizan de fila a columna.
- **Sección activa:** Gumshoe la marca al hacer scroll. Al hacer clic en una sección, la página la centra en pantalla ([scrollIntoView](https://developer.mozilla.org/es/docs/Web/API/Element/scrollIntoView)).
- **En celular** se abre con el botón ☰ ([Offcanvas de Bootstrap](https://getbootstrap.com/docs/5.3/components/offcanvas/#responsive)).

### Inicio
- **Foto de fondo** con una capa café encima para que el texto se lea.
- **Título, texto y botón** entran uno tras otro (Animate.css).
- **Vapor de la taza:** tres líneas onduladas que suben, de [Steam + Coffee Animation](https://codepen.io/evaschicker/pen/WNdMExe) (CodePen).

### Destacados y video
- **Destacados** con miniatura, que entran uno tras otro al hacer scroll (AOS).
- **Botón play** con un pulso, de [Pulsing Play Button](https://codepen.io/jaredringold/pen/zvwWyb) (CodePen).
- **Modal "Nuestro proceso"** con los 4 pasos como línea de tiempo, de [How To - Timeline](https://www.w3schools.com/howto/howto_css_timeline.asp) (W3Schools).

### Galería
- **Al pasar el mouse** la foto se acerca y el título sube. De [Zoom on Hover](https://www.w3schools.com/howto/howto_css_zoom_hover.asp) y [Image Overlay Slide](https://www.w3schools.com/howto/howto_css_image_overlay_slide.asp) (W3Schools).

### Menú
- **Botones de categoría** en vez de una lista desplegable. Filtran igual que antes.
- **Tarjetas** que suben al pasar el mouse (Hover.css) y entran con zoom al aparecer (AOS).
- **La caja cambia de alto suavemente** al filtrar. Técnica de [CSS-Tricks](https://css-tricks.com/using-css-transitions-auto-dimensions/): medir el alto antes y después del cambio y animar entre los dos.

### Nosotros, Promociones y Contacto
- **Nosotros** con foto al lado del texto (grilla de Bootstrap).
- **Promociones** en una franja café oscuro, como en el boceto.
- **Contacto** con [etiquetas flotantes de Bootstrap](https://getbootstrap.com/docs/5.3/forms/floating-labels/).

### Toda la página
- **Rebote al final:** al seguir bajando con la rueda del mouse, la página se estira un poco y vuelve. Usa la [fórmula "rubber band" de iOS](https://gist.github.com/originell/6961057).
- **Menos movimiento:** si la persona activó "reducir movimiento" en su sistema, las animaciones continuas se desactivan.

## Imágenes

Todas son de [Unsplash](https://unsplash.com) y se enlazan por URL:

- Galería (3 fotos)
- Fondo del inicio (granos de café)
- Foto de Nosotros (barista)
- Miniaturas de Espresso, Cappuccino y Cold Brew
