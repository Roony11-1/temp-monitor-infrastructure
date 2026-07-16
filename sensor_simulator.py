import requests
import time
import random

BASE = "http://localhost:80"


def registrar_sensor(mac):
    resp = requests.post(f"{BASE}/api/sensores/registrar", json={"macAddress": mac})
    data = resp.json()
    print(f"[REGISTRAR {mac}] {resp.status_code} -> {data}")
    if resp.status_code != 200:
        code = data.get("code", "N/A")
        msg = data.get("message", str(data))
        print(f"[ERROR] {code}: {msg}")
        return None
    return data["uuid"], data["apiKey"]


def enviar_lectura(sensor_uuid, api_key, temperatura, intento, total):
    headers = {"X-API-KEY": api_key, "X-Sensor-ID": sensor_uuid}
    resp = requests.post(
        f"{BASE}/api/lecturas/sensor/{sensor_uuid}",
        headers=headers,
        json={"temperatura": temperatura}
    )
    if resp.status_code == 200:
        print(f"[LECTURA {intento}/{total}] {resp.status_code} -> {temperatura}°C")
    else:
        err = resp.json()
        code = err.get("code", "N/A")
        msg = err.get("message", str(err))
        print(f"[LECTURA {intento}/{total}] {resp.status_code} -> {code}: {msg}")
    return resp


def consultar_estado(sensor_uuid, api_key):
    headers = {"X-API-KEY": api_key, "X-Sensor-ID": sensor_uuid}
    resp = requests.get(f"{BASE}/api/sensores/{sensor_uuid}/estado", headers=headers)
    print(f"[ESTADO] {resp.status_code} -> {resp.json()}")


# ═══════════════════════════════════════════
# FASE 1 — Registrar todos los sensores
# ═══════════════════════════════════════════
try:
    cantidad_sensores = int(input("¿Cuántos sensores registrar? ").strip())
except ValueError:
    cantidad_sensores = 1

sensores = []
for s in range(cantidad_sensores):
    mac = f"AA:BB:CC:DD:EE:{s:02X}"
    print(f"\n[{s+1}/{cantidad_sensores}] Registrando {mac}...")
    resultado = registrar_sensor(mac)
    if resultado is None:
        print("  ↳ No se pudo registrar.")
        continue
    uuid, apikey = resultado
    sensores.append({"mac": mac, "uuid": uuid, "apiKey": apikey})

if not sensores:
    print("No se registró ningún sensor. Saliendo.")
    exit(1)

print(f"\n✓ {len(sensores)} sensor(es) registrado(s):")
for sen in sensores:
    print(f"   MAC: {sen['mac']}  →  UUID: {sen['uuid']}")

# ═══════════════════════════════════════════
# FASE 2 — Pausa para configurar en el panel
# ═══════════════════════════════════════════
input("\nConfigurá los sensores en el panel (asigná cámara/sucursal) y presioná Enter para continuar...")

# ═══════════════════════════════════════════
# FASE 3 — Configurar y enviar lecturas
# ═══════════════════════════════════════════
try:
    temperatura_promedio = float(input("\nTemperatura promedio (°C): ").strip())
except ValueError:
    temperatura_promedio = 26.0

try:
    cantidad_lecturas = int(input("¿Cuántas lecturas por sensor? ").strip())
except ValueError:
    cantidad_lecturas = 10

try:
    desviacion_pct = float(input("Desviación estándar (%). 0 = todas iguales: ").strip())
except ValueError:
    desviacion_pct = 0

desviacion_temp = temperatura_promedio * (desviacion_pct / 100)
desviacion_cant = cantidad_lecturas * (desviacion_pct / 100)

TIEMPO_BASE = 5  # segundos entre rondas

print(f"\n{'='*60}")
print(f"Enviando lecturas para {len(sensores)} sensor(es)")
print(f"{'='*60}")

# ─── Pre-calcular cuántas lecturas enviará cada sensor ───
for sen in sensores:
    if desviacion_cant == 0:
        sen['n'] = cantidad_lecturas
    else:
        sen['n'] = max(1, round(random.gauss(cantidad_lecturas, desviacion_cant)))

max_n = max(sen['n'] for sen in sensores)

input(f"Presioná Enter para empezar ({max_n} ronda(s) intercalada(s))...")

# ─── Rondas intercaladas ───
for ronda in range(max_n):
    print(f"\n── Ronda {ronda + 1}/{max_n} ──")
    for sen in sensores:
        if ronda < sen['n']:
            if desviacion_temp == 0:
                temp = round(temperatura_promedio, 2)
            else:
                temp = round(random.gauss(temperatura_promedio, desviacion_temp), 2)
            enviar_lectura(sen["uuid"], sen["apiKey"], temp, ronda + 1, sen['n'])

    if ronda < max_n - 1:
        if desviacion_pct == 0:
            espera = TIEMPO_BASE
        else:
            espera = max(0.5, round(random.gauss(TIEMPO_BASE, TIEMPO_BASE * desviacion_pct / 100), 2))
        print(f"  ⏱  Esperando {espera}s...")
        time.sleep(espera)

print(f"\n{'='*60}")
print("Resumen de estados:")
print(f"{'='*60}")
for sen in sensores:
    consultar_estado(sen["uuid"], sen["apiKey"])

print("\n✓ Simulación completa.")
