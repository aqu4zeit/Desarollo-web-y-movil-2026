# language: es
Característica: F08 Panel del personal

  Escenario: CA08-1 Cada trabajador ve lo suyo
    Dado que un trabajador ingresó
    Cuando abre el panel
    Entonces ve solo las pestañas de su perfil

  Escenario: CA08-2 Un cliente no entra al panel
    Dado que un cliente ingresó
    Cuando abre el panel
    Entonces ve que no tiene acceso

  Escenario: CA08-3 Despachar un pedido
    Dado que hay un pedido pagado
    Cuando el encargado lo prepara, lo envía con un chofer y lo entrega
    Entonces el cliente ve el mismo avance en Mi cuenta

  Escenario: CA08-4 No saltarse pasos
    Dado que una orden está pendiente
    Cuando se intenta marcar como entregada
    Entonces el backend lo rechaza

  Escenario: CA08-5 Reparto sin chofer
    Dado que una orden está en preparación
    Cuando se envía sin elegir chofer
    Entonces se pide elegir un chofer

  Escenario: CA08-6 Imprimir la orden
    Dado que el encargado de despacho ve una orden
    Cuando presiona "Imprimir"
    Entonces ve la orden lista para imprimir

  Escenario: CA08-7 Ventas del cajero
    Dado que hay ventas pagadas
    Cuando el cajero abre Ventas
    Entonces ve las ventas de la caja y puede reenviar una boleta

  Escenario: CA08-8 Reporte del dueño
    Dado que hay ventas en el período
    Cuando el dueño pide el reporte entre dos fechas
    Entonces ve el total vendido y los productos más vendidos

  Escenario: CA08-9 Administrar productos
    Dado que el administrador ingresó
    Cuando agrega un producto con stock 0
    Entonces aparece en el menú como "Agotado"

  Escenario: CA08-10 Administrar usuarios
    Dado que el administrador ingresó
    Cuando crea un usuario cajero
    Entonces ese usuario puede ingresar al panel

  Escenario: CA08-11 Ver mensajes de contacto
    Dado que el administrador ingresó
    Cuando abre Mensajes
    Entonces ve los mensajes del formulario de contacto
