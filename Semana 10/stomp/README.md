# Semana 10 — Mensajería con STOMP y Apache ActiveMQ

Productor y consumidor de pedidos de la cafetería construidos en **Python** con la librería **stomp.py**. El productor envía un pedido (id, cliente y monto) a la cola `/queue/pedidos` de **Apache ActiveMQ** usando el protocolo **STOMP**, en uno de cuatro formatos: texto libre, ancho fijo, XML o JSON. El consumidor escucha la cola, interpreta cada mensaje según su formato y confirma la recepción con `ack`; si el mensaje no es válido lo descarta con `nack`.

## Estructura

```
stomp/
├── productor.py      # Envía pedidos a /queue/pedidos
└── consumidor.py     # Escucha /queue/pedidos e interpreta los mensajes
```

## Requisitos

- Python 3.11
- Anaconda (o cualquier gestor de entornos virtuales)
- Apache ActiveMQ (STOMP en el puerto 61613)

## Creación del entorno

```bash
conda create -n stomp python=3.11 -y
conda activate stomp
pip install -r requirements.txt
```

## Ejecución

**ActiveMQ** (PowerShell):

```powershell
activemq start
```

La consola web queda disponible en `http://127.0.0.1:8161`. El broker usa el usuario `demo` con la clave `demo123`.

**Consumidor** (en otra terminal, con el entorno activado):

```powershell
python consumidor.py
```

**Productor** (en otra terminal, con el entorno activado):

```powershell
python productor.py --formato texto --mensaje "Hola desde la cafeteria"
python productor.py --formato fijo --id 1 --cliente "Juan Perez" --monto 5500
python productor.py --formato xml --id 2 --cliente "Maria Gomez" --monto 3200
python productor.py --formato json --id 3 --cliente "Ana Martinez" --monto 4800
```

Para detener el consumidor se presiona `Ctrl+C`.

## Parámetros del productor

| Parámetro | Descripción | Por defecto |
|---|---|---|
| `--formato` | `texto`, `fijo`, `xml` o `json` (obligatorio) | — |
| `--mensaje` | Texto libre para el formato `texto` | `Hola desde la cafeteria` |
| `--id` | Id del pedido | `1` |
| `--cliente` | Nombre del cliente | `Juan Perez` |
| `--monto` | Monto del pedido | `5500` |
| `--host` | Host del broker | `127.0.0.1` |
| `--port` | Puerto STOMP del broker | `61613` |
| `--usuario` | Usuario del broker | `demo` |
| `--clave` | Clave del broker | `demo123` |

El consumidor acepta `--host`, `--port`, `--usuario` y `--clave`.

## Formatos

| Formato | Content-Type | Ejemplo |
|---|---|---|
| texto | `text/plain` | `Hola desde la cafeteria` |
| fijo | `text/plain` | `000001Juan Perez          0005500.00` |
| xml | `application/xml` | `<pedido><id>2</id><cliente>Maria Gomez</cliente><monto>3200</monto></pedido>` |
| json | `application/json` | `{"id": "3", "cliente": "Ana Martinez", "monto": "4800"}` |

El formato fijo tiene 36 caracteres: id (6), cliente (20) y monto (10). El id admite hasta 6 dígitos, el cliente hasta 20 caracteres ASCII y el monto debe estar entre 0 y 99999999.99.
