# Ayudas para las pruebas de integracion contra el sistema levantado con
# preparar.ps1 (guia de autenticacion: pytest e2e/test_stack.py -q).
import json
import pathlib
import random
import re
import subprocess
import time

import httpx
import pytest

BASE = "http://localhost:8000"
CARPETA = pathlib.Path(__file__).resolve().parent.parent

# Usuarios de prueba que crea preparar.ps1
CLAVES = {
    "camila@aroma.cl": "Camila2026!",
    "admin@aroma.cl": "Admin2026!",
    "despacho@aroma.cl": "Despacho2026!",
    "dueno@aroma.cl": "Dueno2026!",
}


def leer_env():
    valores = {}
    for linea in (CARPETA / ".env").read_text().splitlines():
        clave, _, valor = linea.partition("=")
        valores[clave] = valor
    return valores


def compose(*args):
    resultado = subprocess.run(["docker", "compose", *args], cwd=CARPETA,
                               capture_output=True, text=True, encoding="utf-8")
    return resultado.stdout.strip()


def secreto_laboratorio():
    raiz = leer_env()["VAULT_ROOT_TOKEN"]
    return compose("exec", "-T", "-e", "VAULT_ADDR=http://127.0.0.1:8200", "-e", f"VAULT_TOKEN={raiz}",
                   "vault", "vault", "kv", "get", "-field=secret", "secret/tramos/laboratorio-mensajeria")


# Ejecuta Python dentro del contenedor del gateway (red privada): sirve para
# leer el buzon de prueba y para intentar llamar a los servicios sin pasar por el gateway
def en_red_privada(codigo, *args):
    return compose("exec", "-T", "gateway", "python", "-c", codigo, *args)


def correos(correo):
    codigo = ("import httpx, sys, json; print(json.dumps(httpx.get('http://mensajeria:9600/buzon', "
              "params={'correo': sys.argv[1]}, headers={'X-Service-Name': 'laboratorio', "
              "'X-Service-Secret': sys.argv[2]}).json()))")
    return json.loads(en_red_privada(codigo, correo, secreto_laboratorio()) or "[]")


def run_valido():
    cuerpo = str(random.randint(10_000_000, 25_000_000))
    suma, multiplo = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplo
        multiplo = 2 if multiplo == 7 else multiplo + 1
    resto = 11 - suma % 11
    return f"{cuerpo}-{'0' if resto == 11 else 'K' if resto == 10 else resto}"


def ingresar(usuario, clave=None):
    cliente = httpx.Client(base_url=BASE, timeout=10.0)
    r = cliente.post("/auth/login", json={"username": usuario, "password": clave or CLAVES[usuario]})
    assert r.status_code == 200, r.text
    return cliente


def esperar_estado(cliente, pedido_id, estado, intentos=10):
    for _ in range(intentos):
        pedido = cliente.get(f"/api/pedidos/{pedido_id}").json()
        if pedido["estado"] == estado:
            return pedido
        time.sleep(0.5)
    raise AssertionError(f"El pedido {pedido_id} quedó en {pedido['estado']}, se esperaba {estado}")


def pagar_en_pasarela(url_pago, accion="aprobar"):
    # Lo mismo que hace el navegador al pulsar el boton de la pasarela de prueba
    return httpx.post(url_pago, data={"accion": accion}, follow_redirects=False)


@pytest.fixture(scope="session")
def camila():
    return ingresar("camila@aroma.cl")


@pytest.fixture(scope="session")
def admin():
    return ingresar("admin@aroma.cl")


@pytest.fixture(scope="session")
def encargado():
    return ingresar("despacho@aroma.cl")


@pytest.fixture(scope="session")
def dueno():
    return ingresar("dueno@aroma.cl")


@pytest.fixture(scope="session")
def productos():
    lista = httpx.get(f"{BASE}/api/productos").json()
    return {p["nombre"]: p for p in lista}


# Un cliente nuevo registrado por la web y verificado con el codigo del buzon
@pytest.fixture(scope="session")
def cliente_nuevo():
    correo = f"prueba{random.randint(1000, 9999)}@gmail.com"
    datos = {
        "run": run_valido(), "nombre": "Cliente de Prueba", "correo": correo, "password": "Prueba2026!",
        "telefono": "+56944444444", "fecha_nacimiento": "1999-09-09", "sexo": "otro",
        "direccion": "Av. Providencia 1200", "comuna": "Providencia", "provincia": "Santiago",
        "region": "Metropolitana",
    }
    r = httpx.post(f"{BASE}/api/clientes/registro", json=datos)
    assert r.status_code == 201, r.text
    codigo = re.search(r"\d{6}", correos(correo)[-1]["cuerpo"]).group()
    assert httpx.post(f"{BASE}/api/clientes/verificar", json={"correo": correo, "codigo": codigo}).status_code == 200
    return ingresar(correo, "Prueba2026!")
