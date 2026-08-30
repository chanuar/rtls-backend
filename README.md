# RTLS UWB — backend para 5 MaUWB ESP32S3

Backend de posicionamiento preparado para un montaje mínimo de **4 anchors
(A0-A3) y 1 tag móvil (T0)**. Recibe por MQTT una ronda completa de distancias,
la guarda en PostgreSQL, calcula una sola posición por ronda y la publica para
la API y el frontend.

## Arquitectura

```text
T0 móvil ──UWB──> A0, A1, A2, A3
                    │
                    └─ A0 por USB ─> mauwb_gateway.py ─> MQTT
                                                        │
                                  PostgreSQL <─ engine.py ─> posición MQTT
                                                        │
                                                     api.py
```

Con cinco placas solo se puede seguir un objeto/persona: cuatro placas se usan
como referencias fijas y una como tag. Para seguir otra persona hace falta otro
MaUWB configurado como tag. A0 se usa como pasarela porque el firmware AT puede
entregar la ronda del sistema; no se deben conectar varios anchors a la pasarela
porque publicarían medidas duplicadas.

## Puesta en marcha del backend

Requisitos: Docker, Python 3.10 o superior y un cable USB de datos para A0.

```bash
docker compose up -d
python -m venv .venv
```

Activar el entorno e instalar dependencias:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# Linux/macOS
source .venv/bin/activate
pip install -r requirements.txt
```

Arrancar, en terminales separadas:

```bash
python -m rtls.engine
uvicorn rtls.api:app --reload --port 8000
```

Para probar sin placas, una tercera terminal puede ejecutar:

```bash
python tools/simulator.py
```

Comprobaciones:

```bash
curl http://localhost:8000/anchors
curl http://localhost:8000/tags
curl "http://localhost:8000/positions/T0?start=2026-01-01T00:00:00Z&end=2030-01-01T00:00:00Z"
```

La API en vivo está en `ws://localhost:8000/ws/positions`.

> `sql/schema.sql` solo se ejecuta al crear por primera vez el volumen de
> PostgreSQL. Si este proyecto ya se arrancó con el esquema antiguo de seis
> anchors y no hay datos que conservar, `docker compose down -v` y después
> `docker compose up -d` recrean la base. **`-v` borra todos los rangos y
> posiciones almacenados.** Si hay datos útiles, expórtalos y migra las
> coordenadas manualmente.

## Montaje físico

Esta configuración asume el modelo **Makerfabs MaUWB ESP32S3 con firmware AT
para DW3000**, UART a 115200 baudios. Si la placa es la variante DSTO o usa otro
firmware, la línea serie puede tener otro formato y habrá que ajustar la
pasarela.

### 1. Asignar roles e identificadores

Conecta y configura una placa cada vez usando el monitor serie del fabricante.
Carga primero en todas la misma versión del firmware AT. Configuración propuesta:

En el ESP32 de A0 carga el ejemplo oficial de anchor/puente serie que muestra
las líneas `AT+RANGE` en el monitor USB. La pasarela Python lee exactamente esa
salida; un sketch que solo dibuje la pantalla OLED no es suficiente. En las
demás placas usa los ejemplos oficiales de configuración para su papel.

| Placa | Papel | ID numérico | Nombre backend |
|---|---|---:|---|
| 1 | anchor + pasarela USB | 0 | A0 |
| 2 | anchor | 1 | A1 |
| 3 | anchor | 2 | A2 |
| 4 | anchor | 3 | A3 |
| 5 | tag móvil | 0 | T0 |

En el firmware AT de Makerfabs, `role=1` es anchor y `role=0` es tag. Antes del
`SETCFG` de cada placa, envía `AT?` y `AT+RESTORE`, como indica la secuencia
oficial. Después usa:

```text
# A0
AT+SETCFG=0,1,0,1
# A1
AT+SETCFG=1,1,0,1
# A2
AT+SETCFG=2,1,0,1
# A3
AT+SETCFG=3,1,0,1
# T0
AT+SETCFG=0,0,0,1
```

Envía a cada placa, después de su `SETCFG`:

```text
AT+SETCAP=10,15
AT+SETRPT=1
AT+SAVE
AT+RESTART
```

El tercer y cuarto parámetro (`speed=0`, `filter=1`) son los valores iniciales
propuestos. Mantén iguales en todas las placas el canal/PAN y demás parámetros
de radio que exponga tu versión de firmware. Confirma las respuestas `OK` y,
después del reinicio, el ID y papel mostrados por el ejemplo serie. La sintaxis
exacta puede variar entre versiones del
firmware: si un comando responde `ERROR`, usa el ejemplo AT correspondiente a
la versión instalada, sin cambiar el reparto A0-A3/T0.

Referencias del fabricante: [repositorio y secuencia AT de
Makerfabs](https://github.com/Makerfabs/MaUWB_ESP32S3-with-STM32-AT-Command) y
[wiki del MaUWB ESP32S3](https://wiki.makerfabs.com/MaUWB_ESP32S3%20UWB%20module.html).

### 2. Colocar y medir

Usa como origen `(0,0)` la esquina izquierda de la fachada, X hacia el fondo e
Y hacia el lado derecho. Colocación inicial incluida en `sql/schema.sql`:

```text
fachada
A0 (0.5, 0.5, 3.0) ---------------- A1 (0.5, 5.1, 3.0)
        |                                      |
        |               T0                     |  28 m aprox.
        |                                      |
A2 (27.5, 0.5, 3.0) --------------- A3 (27.5, 5.1, 3.0)
fondo
```

- Fija los anchors, con orientación similar, visión lo más despejada posible y
  alimentación USB estable.
- Mide X, Y y Z desde el mismo origen hasta el centro de la antena de cada placa
  y sustituye los valores de `anchors` en la base de datos.
- Lleva T0 aproximadamente a la altura indicada por `RTLS_TAG_HEIGHT` (1,2 m por
  defecto). Cambia esa variable si el tag irá a otra altura.
- En un local largo, estanterías, personas y cámaras frigoríficas producen NLOS.
  Con cuatro anchors se cubre el mínimo geométrico, pero no hay la redundancia
  del diseño original de seis anchors; valida especialmente la zona central.

### 3. Conectar A0 a MQTT

Alimenta A1-A3 y T0. Conecta **solo A0** por USB de datos al ordenador que
ejecutará la pasarela. En Windows localiza su puerto en el Administrador de
dispositivos (por ejemplo `COM5`) y ejecuta:

```powershell
python tools\mauwb_gateway.py --port COM5 --mqtt-host localhost
```

En Linux suele ser similar a:

```bash
python tools/mauwb_gateway.py --port /dev/ttyACM0 --mqtt-host localhost
```

Si Mosquitto está en otro ordenador de la red, cambia `localhost` por su IP LAN,
por ejemplo `--mqtt-host 192.168.1.50`, y permite el puerto TCP 1883 en su
firewall. El motor y la API deben apuntar al mismo broker con
`RTLS_MQTT_HOST=192.168.1.50`.

La pasarela interpreta líneas como:

```text
AT+RANGE=tid:0,mask:0F,seq:182,range:(232,401,518,633),rssi:(...),ancid:(0,1,2,3)
```

El firmware normalmente expresa `range` en centímetros; por eso la escala por
defecto es `0.01`. Coloca T0 a una distancia conocida (por ejemplo 2 m) y revisa
el valor guardado. Si tu firmware entrega milímetros, usa
`--distance-scale 0.001`. Las versiones recientes que no incluyen RSSI también
están soportadas.

## Formato MQTT

Entrada recomendada en `rtls/ranges`:

```json
{
  "tag": "T0",
  "cycle": 182,
  "ts": "2026-08-17T10:30:00Z",
  "ranges": [
    {"anchor": "A0", "distance": 2.32, "rssi": -79.8},
    {"anchor": "A1", "distance": 4.01},
    {"anchor": "A2", "distance": 5.18},
    {"anchor": "A3", "distance": 6.33}
  ]
}
```

El motor valida la ronda, descarta ciclos consecutivos duplicados, registra T0
automáticamente y produce una única posición. También mantiene compatibilidad
con el mensaje antiguo de una medida por publicación.

Salida en `rtls/positions/T0`:

```json
{"tag":"T0","ts":"2026-08-17T10:30:00+00:00","x":4.12,"y":2.87,"quality":0.08,"n_anchors":4}
```

`quality` es el residuo RMS en metros. Un valor sostenido superior a 0,5 suele
indicar coordenadas incorrectas, mala escala, obstáculos o una medida anómala.

## Prueba y calibración

1. Primero ejecuta el simulador y confirma que `/positions/T0` devuelve datos.
2. Detén el simulador y arranca la pasarela serie con las cinco placas encendidas.
3. Deja T0 quieto durante dos minutos en al menos cinco puntos medidos, incluidas
   las esquinas y el centro.
4. Compara la posición de la API con cada punto. Corrige primero coordenadas,
   altura y `--distance-scale`; después ajusta el retardo de antena/calibración
   siguiendo el firmware del fabricante.
5. Repite con personas y estanterías entre T0 y los anchors para medir el error
   real en NLOS.

Ejecutar la comprobación incluida:

```bash
python -m unittest discover -s tests -v
```

## ¿Deben estar conectados al mismo ordenador?

No los cinco. En el montaje implementado, **A0 debe permanecer conectado por USB
al ordenador de la pasarela**, mientras A1-A3 y T0 solo necesitan alimentación y
se comunican por UWB. El backend, la pasarela y el broker pueden estar en
ordenadores distintos si comparten red IP.

Para eliminar también el USB de A0 hay que cargar un firmware ESP32 que lea por
UART2 la salida AT (RX GPIO 18, TX GPIO 17 en este modelo) y publique directamente
por Wi-Fi en MQTT. Ese firmware no forma parte de este repositorio; la pasarela
USB incluida es el camino mínimo y verificable para empezar las pruebas.

## Configuración del servicio

El motor y la API aceptan estas variables principales:

- `RTLS_MQTT_HOST`, `RTLS_MQTT_PORT`, `RTLS_TOPIC_RANGES`.
- `RTLS_DATABASE_URL`.
- `RTLS_MIN_ANCHORS` (3 por defecto; mantener 3 para tolerar una medida ausente).
- `RTLS_TAG_HEIGHT` (1.2 m por defecto).
- `RTLS_KF_PROCESS_NOISE` y `RTLS_KF_MEAS_NOISE` para el filtro.

Mosquitto permite acceso anónimo solo para desarrollo. Antes de usarlo fuera de
una red de pruebas, configura usuarios/TLS, restringe CORS y define una política
de retención para `ranges` y `positions`.
