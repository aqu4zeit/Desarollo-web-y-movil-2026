# language: es
Característica: F05 Recibir promociones

  Escenario: CA05-1 Suscribirse
    Dado que el cliente ingresó
    Cuando presiona el botón de promociones
    Entonces queda suscrito con el correo de su cuenta

  Escenario: CA05-2 Desuscribirse
    Dado que el cliente está suscrito
    Cuando desactiva las promociones en Mi cuenta
    Entonces deja de estar suscrito

  Escenario: CA05-3 Sin sesión
    Dado que el visitante no ha ingresado
    Cuando presiona el botón de promociones
    Entonces se le pide ingresar o crear una cuenta

  Escenario: CA05-4 Un trabajador no puede suscribirse
    Dado que el cajero ingresó
    Cuando intenta suscribirse
    Entonces el backend responde 403
