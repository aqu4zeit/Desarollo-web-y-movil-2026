# language: es
Característica: F04 Ingresar y salir

  Escenario: CA04-1 Ingreso de un cliente
    Dado que el cliente tiene una cuenta verificada
    Cuando ingresa con su correo y clave
    Entonces ve su nombre y "Mi cuenta" en la barra lateral

  Escenario: CA04-2 Ingreso de un trabajador
    Dado que el cajero tiene una cuenta
    Cuando ingresa con su correo y clave
    Entonces ve "Panel" en la barra lateral

  Escenario: CA04-3 La sesión se mantiene
    Dado que el cliente ya ingresó
    Cuando recarga la página
    Entonces sigue con la sesión iniciada

  Escenario: CA04-4 Clave incorrecta
    Dado que el cliente escribió mal su clave
    Cuando presiona "Ingresar"
    Entonces ve "Correo o clave incorrectos"

  Escenario: CA04-5 Cuenta sin verificar
    Dado que el cliente no verificó su correo
    Cuando intenta ingresar
    Entonces se le pide verificar el correo

  Escenario: CA04-6 Demasiados intentos
    Dado que se intentó ingresar más de 10 veces en un minuto
    Cuando se intenta otra vez
    Entonces se pide esperar un minuto

  Escenario: CA04-7 Salir
    Dado que el cliente ya ingresó
    Cuando presiona "Salir"
    Entonces la sesión se cierra y vuelve a ver "Ingresar"

  Escenario: CA04-8 Sesión vencida
    Dado que pasaron más de 15 minutos desde el ingreso
    Cuando el cliente hace una acción que necesita sesión
    Entonces se le pide ingresar de nuevo
