# Semana 6 — API REST con FastAPI + MongoDB

API REST local construida con **FastAPI**, **Motor** (driver asíncrono de MongoDB) y **Pydantic**, sobre la colección `clientes` de la base `UNAB` en MongoDB.

## Requisitos

- Python 3.10+
- MongoDB corriendo en `localhost:27017`

## Instalación

```bash
pip install -r requirements.txt
```

## Ejecución

```bash
uvicorn main_clientes:app --reload
```

- API: http://127.0.0.1:8000
- Documentación interactiva (Swagger): http://127.0.0.1:8000/docs
- Documentación (ReDoc): http://127.0.0.1:8000/redoc

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado del servicio |
| GET | `/clientes` | Lista clientes, con filtro `q` (por nombre), `skip` y `limit` |
| POST | `/clientes` | Crea un cliente (201) |
| GET | `/clientes/{cliente_id}` | Obtiene un cliente por id |
| PUT | `/clientes/{cliente_id}` | Actualiza un cliente |
| DELETE | `/clientes/{cliente_id}` | Elimina un cliente (204) |

### Modelo `Cliente`

```json
{
  "nombre": "string",
  "pass": "string"
}
```

`id` se agrega automáticamente en las respuestas (viene del `_id` de MongoDB).
