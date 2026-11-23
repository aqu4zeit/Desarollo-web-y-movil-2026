# language: es
Característica: F06 Hacer un pedido y pagarlo

  Escenario: CA06-1 Armar el carrito
    Dado que el cliente ingresó
    Cuando agrega 2 Cappuccino y 1 Croissant
    Entonces el carrito muestra un total de $8.900

  Escenario: CA06-2 Pedido pagado
    Dado que el carrito tiene productos
    Cuando confirma el pedido y aprueba el pago
    Entonces el pedido queda pagado y recibe la boleta en su correo

  Escenario: CA06-3 El precio lo decide el backend
    Dado que alguien cambió el precio en el navegador
    Cuando confirma el pedido
    Entonces el total es el que calcula el backend

  Escenario: CA06-4 Doble clic
    Dado que el carrito tiene productos
    Cuando presiona "Confirmar pedido" dos veces
    Entonces se crea un solo pedido

  Escenario: CA06-5 Sin stock
    Dado que queda 1 Croissant
    Cuando el cliente pide 3
    Entonces ve que no hay stock suficiente

  Escenario: CA06-6 Fuera del área de despacho
    Dado que el cliente vive en una comuna sin despacho
    Cuando confirma el pedido
    Entonces ve que no hay despacho a su comuna

  Escenario: CA06-7 Pago rechazado
    Dado que el cliente tiene un pedido sin pagar
    Cuando rechaza el pago
    Entonces el pedido sigue pendiente y puede pagarlo después

  Escenario: CA06-8 Sin sesión
    Dado que el visitante no ha ingresado
    Cuando presiona "Confirmar pedido"
    Entonces se le pide ingresar y el carrito se conserva

  Escenario: CA06-9 Servicio caído
    Dado que el servicio de pedidos está detenido
    Cuando el cliente confirma el pedido
    Entonces ve que no se pudo crear y el carrito se conserva
