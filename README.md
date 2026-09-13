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

Requisitos: Docker Compose y **Python 3.14.7**. Para usar las placas,
necesitas un cable USB de datos para A0.

Docker Compose arranca PostgreSQL y Mosquitto. Con Python 3.14.7 seleccionado:

```bash
docker compose up -d
python -m venv .venv
```

Activar el entorno e instalar dependencias:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock.txt
```

```bash
# Linux/macOS
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.lock.txt` fija todas las dependencias para Windows x64.
En Linux/macOS se usa `requirements.txt` para resolver las dependencias
específicas del sistema; la instalación en esas plataformas no se ha verificado.

Arrancar, en terminales separadas:

```bash
python -m rtls.engine
python -m rtls.api  # Windows
# uvicorn rtls.api:app --reload --port 8000  # Linux/macOS
```

Para probar sin placas, una tercera terminal puede ejecutar:

```bash
python -m tools.simulator
```

Comprobaciones:

```bash
curl http://localhost:8000/anchors
curl http://localhost:8000/tags
curl "http://localhost:8000/positions/T0?start=2026-01-01T00:00:00Z&end=2030-01-01T00:00:00Z"
```

La API en vivo está en `ws://localhost:8000/ws/positions`.

> `sql/schema.sql` solo se ejecuta al crear por primera vez el volumen de
> PostgreSQL. Para una base existente, revisa `sql/update_measured_anchors.sql`
> y aplícalo solo si coincide con tu montaje. Desde PowerShell:
>
> ```powershell
> Get-Content sql/update_measured_anchors.sql | docker compose exec -T postgres psql -U rtls -d rtls -v ON_ERROR_STOP=1
> ```
>
> Conserva rangos y posiciones históricos; las posiciones antiguas no se
> recalculan. Anota la fecha del cambio de calibración para interpretar el
> histórico. El motor relee las coordenadas con el siguiente mensaje.

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
AT+SETCFG=0,1,1,1
# A1
AT+SETCFG=1,1,1,1
# A2
AT+SETCFG=2,1,1,1
# A3
AT+SETCFG=3,1,1,1
# T0
AT+SETCFG=0,0,1,1
```

Envía a cada placa, después de su `SETCFG`:

```text
AT+SETCAP=10,10,0
AT+SETRPT=1
AT+SAVE
AT+RESTART
```

El tercer y cuarto parámetro (`speed=1`, 6.8 Mbps; `filter=1`) y `SETCAP`
coinciden con los sketches de `../arduino` para firmware AT reciente.
Mantén iguales en todas las placas el canal/PAN y demás parámetros
de radio que exponga tu versión de firmware. Confirma las respuestas `OK` y,
después del reinicio, el ID y papel mostrados por el ejemplo serie. La sintaxis
exacta puede variar entre versiones del
firmware: si un comando responde `ERROR`, usa el ejemplo AT correspondiente a
la versión instalada, sin cambiar el reparto A0-A3/T0.

Referencias del fabricante: [repositorio y secuencia AT de
Makerfabs](https://github.com/Makerfabs/MaUWB_ESP32S3-with-STM32-AT-Command) y
[wiki del MaUWB ESP32S3](https://wiki.makerfabs.com/MaUWB_ESP32S3%20UWB%20module.html).

### 2. Colocar y medir

Segundo montaje de prueba del 2026-09-08: A0 `(12.0, 0.27, 2.0)`,
A1 `(1.6, 0.8, 1.9)`, A2 `(1.6, 5.6, 2.0)` y A3 `(12.4, 4.6, 2.0)` m.
La actualización explícita está en `sql/anchors_trial_2026_09_08_02.sql`;
después aplica `sql/anchors_trial_2026_09_08_03.sql` para corregir A1/A2.
se aplica con el mismo comando `psql` indicado arriba, cambiando el archivo.
T0 irá aproximadamente a 1.0 m: usa `RTLS_TAG_HEIGHT=1.0` (valor por defecto).
El montaje anterior se conserva en `sql/anchors_trial_2026_09_08.sql`.

Usa como origen `(0,0)` la esquina izquierda de la fachada, X hacia el fondo e
Y hacia el lado derecho. Colocación inicial incluida en `sql/schema.sql`:

```text
A0 = (6.20, 2.20, 0.80)  pasarela USB
A1 = (7.37, 4.40, 0.80)
A2 = (0.00, 4.40, 0.80)
A3 = (0.00, 0.67, 0.80)
Local aproximado: 7.4 m de profundidad × 4.4 m de anchura
```

- Fija los anchors, con orientación similar, visión lo más despejada posible y
  alimentación USB estable.
- Mide X, Y y Z desde el mismo origen hasta el centro de la antena de cada placa
  y sustituye los valores de `anchors` en la base de datos.
- Lleva T0 aproximadamente a la altura indicada por `RTLS_TAG_HEIGHT` (1,0 m por
  defecto). Cambia esa variable si el tag irá a otra altura.
- Estanterías, personas y cámaras frigoríficas producen NLOS. Cuatro anchors
  permiten comprobar la coherencia del ajuste 2D, pero no identificar siempre
  cuál de las medidas es incorrecta.

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
python -m pip check
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
- `RTLS_TAG_HEIGHT` (1.0 m por defecto).
- `RTLS_RANGE_HEIGHT_TOLERANCE` (0.1 m): tolerancia de ruido cuando la distancia
  medida es menor que la separación vertical. Ajustar con medidas reales.
- `RTLS_MAX_RMS` (1.0 m): residuo máximo aceptado antes de actualizar el filtro.
  Se acepta RMS <= 1.0 m y se rechaza RMS > 1.0 m por defecto. Es el residuo
  del ajuste, no un límite de distancia entre tag y anchor ni una garantía de
  precisión de 1 m. La variable de entorno permite ajustar este umbral.
- `RTLS_KF_PROCESS_NOISE` y `RTLS_KF_MEAS_NOISE` para el filtro.

El motor relee las coordenadas antes de cada mensaje y reinicia los filtros y
rangos en memoria si cambian. Las medidas físicamente imposibles se conservan
en la base, pero no se usan para posicionar. Se requieren al menos tres rangos
válidos de anchors no colineales. Las posiciones rechazadas no actualizan el
filtro; el RMS describe el ajuste previo al suavizado, no garantiza precisión.

Se calcula `d_horizontal = sqrt(d_3D² - (z_anchor - z_tag)²)` y se ajustan
X e Y minimizando los residuos de distancia horizontal. Z se fija a
`RTLS_TAG_HEIGHT`: no se estima la altura. Con las alturas iniciales, la
separación vertical es 0.2 m. Los arranques múltiples reducen la dependencia
de la posición anterior del solver; el filtro Kalman suaviza después.

Se usan todos los rangos físicamente válidos disponibles. Si su RMS supera el
umbral, se rechaza la posición completa: no se elimina el anchor que permita
obtener el menor RMS. Tres anchors no colineales permiten calcular X/Y si falta
una medida, con menos información para detectar errores. Para exigir cuatro,
configura `RTLS_MIN_ANCHORS=4`. Incluso un RMS bajo puede acompañar errores de
posición por geometría, NLOS o alturas incorrectas; valida con puntos medidos.

El simulador produce solo T0 y carga A0-A3 desde PostgreSQL al arrancar; usa
la altura, broker y topic de la configuración del motor. Reinícialo si cambias
las coordenadas. Su recorrido usa los límites X/Y de los anchors, sin modelar
paredes ni obstáculos. Detén la pasarela real antes de simular con el mismo T0.

Las medidas atrasadas no actualizan el seguimiento. Tras una pérdida de conexión
PostgreSQL, el motor intenta reconectar con el siguiente mensaje; las rondas
recibidas durante la caída no se recuperan automáticamente (MQTT QoS 0).
La API renueva su suscripción MQTT en cada reconexión.
Cada consulta REST abre y cierra su propia conexión PostgreSQL, con un timeout
de conexión de 3 segundos. Si la conexión o consulta falla por pérdida de la
base de datos, devuelve HTTP 503; la siguiente petición vuelve a conectar,
sin necesidad de reiniciar la API.

Mosquitto permite acceso anónimo solo para desarrollo. Antes de usarlo fuera de
una red de pruebas, configura usuarios/TLS, restringe CORS y define una política
de retención para `ranges` y `positions`.
