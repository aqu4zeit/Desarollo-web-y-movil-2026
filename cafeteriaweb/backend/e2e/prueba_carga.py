# Prueba de carga reproducible con httpx asincrono (respaldo del ADR de gRPC y analitica).
# Usuarios virtuales concurrentes recorren el sitio por el API Gateway y se mide
# latencia (p50, p95, p99), throughput y errores por operacion.
#
# El gateway limita 120 solicitudes por minuto por IP y esta prueba sale de una sola IP,
# asi que el limite se sube solo mientras se mide (desde backend/):
#   $env:LIMITE_POR_MINUTO="100000"; docker compose up -d gateway
#   python e2e/prueba_carga.py --usuarios 20 --segundos 60
#   python e2e/prueba_carga.py --usuarios 50 --segundos 60 --agregar
#   Remove-Item Env:LIMITE_POR_MINUTO; docker compose up -d gateway
import argparse
import asyncio
import os
import pathlib
import platform
import random
import statistics
import time
from datetime import datetime

import httpx

CARPETA = pathlib.Path(__file__).resolve().parent.parent

BASE = "http://localhost:8000"
CONSULTA = "{ misPedidos(primeros: 10) { id estado total items { nombre cantidad } pago { estado } despacho { estado } } }"


class Medidor:
    def __init__(self):
        self.tiempos = {}
        self.errores = {}

    async def medir(self, nombre, solicitud, esperado):
        inicio = time.perf_counter()
        respuesta = None
        try:
            respuesta = await solicitud
        except httpx.HTTPError:
            pass
        self.tiempos.setdefault(nombre, []).append((time.perf_counter() - inicio) * 1000)
        if respuesta is not None and respuesta.status_code == 429:
            raise SystemExit("El gateway respondió 429: sube LIMITE_POR_MINUTO antes de medir (ver cabecera).")
        if respuesta is None or respuesta.status_code != esperado:
            self.errores[nombre] = self.errores.get(nombre, 0) + 1
        return respuesta


# Consumo de CPU y memoria de cada contenedor mientras dura la prueba (docker stats)
def a_mib(texto):
    numero = float(texto.rstrip("KiMGB"))
    return numero / 1024 if texto.endswith("KiB") else numero * 1024 if texto.endswith("GiB") else numero


async def medir_recursos(fin, maximos):
    while time.monotonic() < fin:
        proceso = await asyncio.create_subprocess_exec(
            "docker", "stats", "--no-stream", "--format", "{{.Name}};{{.CPUPerc}};{{.MemUsage}}",
            stdout=asyncio.subprocess.PIPE, cwd=CARPETA)
        salida, _ = await proceso.communicate()
        for linea in salida.decode().splitlines():
            nombre, cpu, memoria = linea.split(";")
            servicio = nombre.replace("aroma-", "").rsplit("-", 1)[0]
            actual = maximos.setdefault(servicio, {"cpu": 0.0, "mem": 0.0})
            actual["cpu"] = max(actual["cpu"], float(cpu.rstrip("%")))
            actual["mem"] = max(actual["mem"], a_mib(memoria.split(" / ")[0]))


def percentil(valores, p):
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(round(p / 100 * (len(ordenados) - 1))))]


async def usuario_virtual(sesion, medidor, fin, productos):
    async with httpx.AsyncClient(base_url=BASE, timeout=10.0) as anonimo:
        while time.monotonic() < fin:
            # Visitante: mira el catalogo (lo mas frecuente)
            await medidor.medir("GET /api/productos", anonimo.get("/api/productos"), 200)
            await medidor.medir("GET /api/categorias", anonimo.get("/api/categorias"), 200)
            # Cliente con sesion: revisa sus pedidos (GraphQL: orders + payments + despacho + inventory)
            await medidor.medir("POST /api/graphql (misPedidos)", sesion.post("/api/graphql", json={"query": CONSULTA}), 200)
            # Uno de cada cuatro ciclos crea un pedido y lo anula (reserva y devolucion de stock)
            if random.random() < 0.25:
                producto = random.choice(productos)
                r = await medidor.medir("POST /api/pedidos",
                                        sesion.post("/api/pedidos", json={"items": [{"producto_id": producto, "cantidad": 1}]}),
                                        201)
                if r is not None and r.status_code == 201:
                    await medidor.medir("POST /api/pedidos/{id}/anular",
                                        sesion.post(f"/api/pedidos/{r.json()['id']}/anular", json={"motivo": "Prueba de carga"}),
                                        200)
            await asyncio.sleep(random.uniform(0.1, 0.5))


async def principal(usuarios, segundos, sesiones):
    async with httpx.AsyncClient(base_url=BASE) as c:
        productos = [p["id"] for p in (await c.get("/api/productos")).json() if p["stock"] > 20]
    # Pocas sesiones compartidas (el login tiene su propio limite por minuto)
    clientes = []
    for _ in range(sesiones):
        cliente = httpx.AsyncClient(base_url=BASE, timeout=10.0)
        r = await cliente.post("/auth/login", json={"username": "camila@aroma.cl", "password": "Camila2026!"})
        if r.status_code != 200:
            raise SystemExit(f"No fue posible iniciar sesión ({r.status_code}). Espera un minuto y reintenta.")
        clientes.append(cliente)

    medidor = Medidor()
    recursos = {}
    inicio = time.monotonic()
    fin = inicio + segundos
    await asyncio.gather(medir_recursos(fin, recursos),
                         *[usuario_virtual(clientes[i % sesiones], medidor, fin, productos) for i in range(usuarios)])
    duracion = time.monotonic() - inicio
    for cliente in clientes:
        await cliente.post("/auth/logout")
        await cliente.aclose()
    return medidor, duracion, recursos


def informe(medidor, duracion, usuarios, segundos, recursos):
    total = sum(len(v) for v in medidor.tiempos.values())
    errores = sum(medidor.errores.values())
    filas = ["| Operación | Solicitudes | Errores | p50 (ms) | p95 (ms) | p99 (ms) | Máx (ms) |",
             "|---|---|---|---|---|---|---|"]
    for nombre, tiempos in medidor.tiempos.items():
        filas.append(f"| {nombre} | {len(tiempos)} | {medidor.errores.get(nombre, 0)} | "
                     f"{statistics.median(tiempos):.0f} | {percentil(tiempos, 95):.0f} | "
                     f"{percentil(tiempos, 99):.0f} | {max(tiempos):.0f} |")
    todos = [t for v in medidor.tiempos.values() for t in v]
    consumo = ["| Contenedor | CPU máx. (%) | Memoria máx. (MiB) |", "|---|---|---|"]
    for servicio, valores in sorted(recursos.items(), key=lambda x: -x[1]["cpu"]):
        consumo.append(f"| {servicio} | {valores['cpu']:.1f} | {valores['mem']:.0f} |")
    return "\n".join([
        f"# Prueba de carga — {datetime.now():%d-%m-%Y %H:%M} (medición, no proyección)",
        "",
        f"- Entorno: {platform.system()} {platform.release()}, {os.cpu_count()} CPU lógicas, Docker Desktop; "
        "un proceso uvicorn por servicio, una instancia de MongoDB 8.0.",
        f"- Usuarios virtuales concurrentes: {usuarios}, duración: {segundos} s, todo por el API Gateway (localhost:8000).",
        f"- Total: {total} solicitudes en {duracion:.1f} s → **{total / duracion:.1f} solicitudes/s**.",
        f"- Errores: {errores} ({100 * errores / max(total, 1):.2f} %). p95 global: **{percentil(todos, 95):.0f} ms**.",
        "",
        *filas,
        "",
        "Consumo máximo observado durante la prueba (`docker stats`, 100 % = 1 CPU):",
        "",
        *consumo,
    ])


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Prueba de carga de Aroma & Café")
    argumentos.add_argument("--usuarios", type=int, default=20)
    argumentos.add_argument("--segundos", type=int, default=60)
    argumentos.add_argument("--sesiones", type=int, default=5)
    argumentos.add_argument("--agregar", action="store_true", help="agrega el resultado al archivo en vez de reemplazarlo")
    a = argumentos.parse_args()
    medidor, duracion, recursos = asyncio.run(principal(a.usuarios, a.segundos, a.sesiones))
    texto = informe(medidor, duracion, a.usuarios, a.segundos, recursos)
    print(texto)
    destino = pathlib.Path(__file__).parent / "resultados_carga.md"
    anterior = destino.read_text(encoding="utf-8") + "\n" if a.agregar and destino.exists() else ""
    destino.write_text(anterior + texto + "\n", encoding="utf-8")
    print(f"\nResultado guardado en {destino}")
