# Aroma & Café — Frontend

Página web de la cafetería Aroma & Café, proyecto del ramo Desarrollo Web y Móvil (NRC 8481, UNAB).

Página publicada: https://aqu4zeit.github.io/Desarollo-web-y-movil-2026/cafeteriaweb/

## Estructura

```
cafeteriaweb/
├── index.html      # página única con todas las secciones
├── css/
│   └── estilos.css # paleta (Propuesta 1, Semana 4) y estilos
└── js/
    └── app.js      # datos, menú, filtro, formularios y animaciones
```

## Cómo verla en local

Abrir `index.html` en el navegador, o levantar un servidor en la carpeta:

```
py -m http.server 5500
```

y entrar a http://localhost:5500

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
