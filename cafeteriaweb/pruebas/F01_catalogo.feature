# language: es
Característica: F01 Consultar el menú

  Escenario: CA01-1 Ver el menú
    Dado que el backend está funcionando
    Cuando el visitante abre la página
    Entonces ve los productos y precios del backend

  Escenario: CA01-2 Ver los destacados
    Dado que el backend está funcionando
    Cuando el visitante abre la página
    Entonces ve Espresso, Cappuccino y Cold Brew como destacados

  Escenario: CA01-3 Filtrar por categoría
    Dado que el menú ya cargó
    Cuando el visitante elige "Pastelería"
    Entonces ve solo Croissant y Cheesecake

  Escenario: CA01-4 Producto sin stock
    Dado que el Croissant tiene stock 0
    Cuando el visitante abre la página
    Entonces el Croissant aparece como "Agotado"

  Escenario: CA01-5 Servicio caído
    Dado que el servicio de productos está detenido
    Cuando el visitante abre la página
    Entonces ve "El menú no está disponible" y un botón "Reintentar"

  Escenario: CA01-6 Recuperación
    Dado que el servicio de productos volvió a funcionar
    Cuando el visitante presiona "Reintentar"
    Entonces el menú se carga sin recargar la página
