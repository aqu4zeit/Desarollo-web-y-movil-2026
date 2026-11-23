# language: es
Característica: F03 Crear cuenta y verificar el correo

  Escenario: CA03-1 Registro correcto
    Dado que el visitante completó sus datos correctamente
    Cuando presiona "Crear cuenta"
    Entonces recibe un código de 6 dígitos en su correo

  Escenario: CA03-2 Verificar el correo
    Dado que el visitante tiene su código
    Cuando lo escribe y presiona "Verificar"
    Entonces ve "Correo verificado, ya puedes ingresar"

  Escenario: CA03-3 RUN inválido
    Dado que el visitante escribió un RUN incorrecto
    Cuando presiona "Crear cuenta"
    Entonces ve que el RUN no es válido

  Escenario: CA03-4 Correo ya registrado
    Dado que ya existe una cuenta con ese correo
    Cuando el visitante intenta registrarse
    Entonces ve "Ya existe una cuenta con ese correo o RUN."

  Escenario: CA03-5 Código incorrecto
    Dado que el visitante se registró
    Cuando escribe un código equivocado
    Entonces ve que el código no es válido

  Escenario: CA03-6 Código vencido o muchos intentos
    Dado que pasaron 15 minutos o falló 5 veces
    Cuando intenta verificar
    Entonces se le ofrece "Enviar otro código"

  Escenario: CA03-7 Reenviar el código
    Dado que el código venció
    Cuando presiona "Enviar otro código"
    Entonces recibe un código nuevo que sí funciona

  Escenario: CA03-8 Servicio caído
    Dado que el servicio de clientes está detenido
    Cuando presiona "Crear cuenta"
    Entonces ve que el registro no está disponible y conserva sus datos
