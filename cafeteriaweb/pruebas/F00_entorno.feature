# language: es
Característica: F00 Entorno de integración

  Escenario: CA00-1 Levantar el backend
    Dado que Docker está vacío
    Cuando se ejecuta .\preparar.ps1
    Entonces los 12 servicios quedan funcionando

  Escenario: CA00-2 La página puede usar el backend
    Dado que la página está en http://localhost:5500
    Cuando pide el menú al gateway
    Entonces el navegador recibe la respuesta sin error de CORS

  Escenario: CA00-3 Otro sitio no puede usar el backend
    Dado que una página de otro sitio llama al gateway
    Cuando el navegador recibe la respuesta
    Entonces la bloquea por CORS

  Escenario: CA00-4 Cada acción se puede rastrear
    Dado que la página hizo una solicitud
    Cuando se revisa la consola del navegador
    Entonces el mismo id de correlación aparece en el log del gateway
