# language: es
Característica: F02 Enviar un mensaje de contacto

  Escenario: CA02-1 Mensaje enviado
    Dado que el visitante completó nombre, correo y mensaje
    Cuando presiona "Enviar"
    Entonces ve un aviso de éxito y el mensaje queda guardado

  Escenario: CA02-2 Faltan datos
    Dado que el visitante dejó un campo vacío
    Cuando presiona "Enviar"
    Entonces ve "Debes completar todos los campos."

  Escenario: CA02-3 Correo mal escrito
    Dado que el visitante escribió "ana@correo"
    Cuando presiona "Enviar"
    Entonces ve "Ingresa un correo válido."

  Escenario: CA02-4 Texto muy corto
    Dado que el visitante escribió un nombre de 2 letras
    Cuando presiona "Enviar"
    Entonces ve que el nombre debe tener al menos 3 caracteres

  Escenario: CA02-5 El backend rechaza datos inválidos
    Dado que alguien envía un correo inválido sin usar la página
    Cuando el backend lo revisa
    Entonces responde 422 y no guarda nada

  Escenario: CA02-6 Servicio caído
    Dado que el servicio de mensajes está detenido
    Cuando el visitante presiona "Enviar"
    Entonces ve que el servicio no está disponible y conserva lo escrito

  Escenario: CA02-7 Reintento
    Dado que el servicio de mensajes volvió a funcionar
    Cuando el visitante presiona "Enviar" otra vez
    Entonces el mensaje se guarda una sola vez
