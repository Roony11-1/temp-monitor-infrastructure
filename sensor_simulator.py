import json
import os
import requests
import time
import random

BASE = "http://localhost:80"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "sensores_cache.json")


ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "admin123"

_jwt_token = None


def _login_admin():
    global _jwt_token
    if _jwt_token:
        return _jwt_token
    try:
        r = requests.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=5)
        if r.status_code == 200:
            _jwt_token = r.json()["token"]
            print(f"  ✓ Admin autenticado como {ADMIN_EMAIL}")
            return _jwt_token
        print(f"  ✗ Error al autenticar admin: {r.status_code} {r.text}")
    except requests.RequestException as e:
        print(f"  ✗ Error de conexión al autenticar admin: {e}")
    return None


def _cargar_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def _guardar_cache(mac, uuid, api_key):
    cache = _cargar_cache()
    cache[mac] = {"uuid": uuid, "apiKey": api_key}
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def registrar_sensor(mac):
    resp = requests.post(f"{BASE}/api/sensores/registrar", json={"macAddress": mac})
    data = resp.json()
    print(f"[REGISTRAR {mac}] {resp.status_code} -> {data}")

    if resp.status_code == 200:
        uuid, api_key = data["uuid"], data["apiKey"]
        _guardar_cache(mac, uuid, api_key)
        return uuid, api_key

    code = data.get("code", "")
    msg = data.get("message", str(data))
    print(f"[ERROR] {code}: {msg}")

    if resp.status_code == 409:
        cache = _cargar_cache()
        if mac in cache:
            print(f"  ↳ Recuperado del caché local → UUID: {cache[mac]['uuid']}")
            return cache[mac]["uuid"], cache[mac]["apiKey"]

        jwt = _login_admin()
        if jwt:
            headers = {"Authorization": f"Bearer {jwt}"}
            r = requests.post(
                f"{BASE}/api/sensores/renew-api-key-by-mac",
                headers=headers,
                json={"macAddress": mac},
            )
            if r.status_code == 200:
                d = r.json()
                print(f"  ↳ API key renovada → UUID: {d['uuid']}")
                _guardar_cache(mac, d["uuid"], d["apiKey"])
                return d["uuid"], d["apiKey"]
            else:
                err = r.json()
                print(f"  ↳ Error al renovar: {err.get('code')} – {err.get('message', err)}")
        print("  ↳ No se pudo recuperar. Se omite.")

    return None


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


def sensor_activo(sensor_uuid, api_key):
    headers = {"X-API-KEY": api_key, "X-Sensor-ID": sensor_uuid}
    try:
        resp = requests.get(f"{BASE}/api/sensores/{sensor_uuid}/estado", headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.text.strip('"') == "ACTIVO"
    except requests.RequestException:
        pass
    return False


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
        print("  ↳ No se pudo registrar ni recuperar del caché. Se omite.")
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

# ─── Verificar qué sensores están ACTIVOS (configurados en el panel) ───
print(f"\n{'='*60}")
print("Verificando estado de los sensores...")
print(f"{'='*60}")
sensores_activos = []
for sen in sensores:
    if sensor_activo(sen["uuid"], sen["apiKey"]):
        print(f"  ✓ {sen['mac']} → ACTIVO")
        sensores_activos.append(sen)
    else:
        print(f"  ✗ {sen['mac']} → NO ACTIVO (se omite)")

if not sensores_activos:
    print("\nNingún sensor está ACTIVO. Saliendo.")
    exit(0)

sensores = sensores_activos

print(f"\n{'='*60}")
print(f"Enviando lecturas para {len(sensores)} sensor(es) ACTIVO(s)")
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
