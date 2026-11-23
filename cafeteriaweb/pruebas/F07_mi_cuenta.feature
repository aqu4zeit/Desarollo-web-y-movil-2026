# language: es
Característica: F07 Mi cuenta

  Escenario: CA07-1 Ver mis pedidos
    Dado que el cliente ingresó y tiene pedidos
    Cuando abre Mi cuenta
    Entonces ve cada pedido con su estado, pago y despacho

  Escenario: CA07-2 Ver la boleta
    Dado que el cliente tiene un pedido pagado
    Cuando presiona "Ver boleta"
    Entonces ve el folio, los productos y el total

  Escenario: CA07-3 Anular un pedido
    Dado que el pedido está pagado y no se ha preparado
    Cuando lo anula indicando un motivo
    Entonces el pedido queda anulado y se devuelve el pago

  Escenario: CA07-4 Pedido que ya no se puede anular
    Dado que el pedido ya está en preparación
    Cuando intenta anularlo
    Entonces ve que ya no se puede anular

  Escenario: CA07-5 Pedido de otro cliente
    Dado que un cliente conoce el id de un pedido ajeno
    Cuando intenta verlo
    Entonces no recibe ningún dato de ese pedido

  Escenario: CA07-6 Sin sesión
    Dado que el visitante no ha ingresado
    Cuando abre Mi cuenta
    Entonces se le pide ingresar

  Escenario: CA07-7 Cambiar mis datos
    Dado que el cliente está en Mi cuenta
    Cuando cambia su dirección y guarda
    Entonces al recargar ve la dirección nueva

  Escenario: CA07-8 Falla el servicio de pagos
    Dado que el servicio de pagos está detenido
    Cuando el cliente abre Mi cuenta
    Entonces ve sus pedidos con un aviso de que el pago no se pudo consultar

  Escenario: CA07-9 Consulta GraphQL demasiado grande
    Dado que alguien envía una consulta de más de 6 niveles
    Cuando GraphQL la revisa
    Entonces la rechaza
