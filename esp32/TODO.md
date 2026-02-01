# Robofocus ESP32 - Stato del Progetto e TODO

## Panoramica

Server ASCOM Alpaca per ESP32 che controlla un focuser Robofocus via protocollo seriale.
Permette il controllo del focuser da software astronomici come NINA, SGP, etc.

## Architettura

```
┌─────────────────────────────────────────────────────────────┐
│                        ESP32                                 │
├─────────────────────────────────────────────────────────────┤
│  main.py           - Entry point, boot sequence             │
│  wifi_manager.py   - WiFi STA/AP mode management            │
│  web_server.py     - HTTP server async lightweight          │
│  alpaca_api.py     - ASCOM Alpaca REST API endpoints        │
│  gui_api.py        - Web GUI REST endpoints                 │
│  discovery.py      - UDP discovery (port 32227)             │
│  controller.py     - Logica focuser, dual mode support      │
│  serial_protocol.py- Protocollo seriale Robofocus           │
│  simulator.py      - Simulatore focuser (no hardware)       │
│  config.py         - Configurazione NVS (persistente)       │
│  log_buffer.py     - Buffer circolare per logs              │
├─────────────────────────────────────────────────────────────┤
│  static/index.html - Control Panel web GUI                  │
│  static/setup.html - WiFi configuration page                │
│  static/logs.html  - System logs viewer                     │
└─────────────────────────────────────────────────────────────┘
```

## Flusso di Boot

1. Se nessun WiFi configurato → AP mode (`Robofocus-XXXX`)
2. Utente si connette all'AP e configura WiFi via `setup.html`
3. ESP32 si connette alla rete WiFi configurata
4. In STA mode: attiva API Alpaca + Discovery + Web GUI
5. Monitor WiFi: se perde connessione, fallback ad AP mode

## Cosa Funziona

- [x] AP mode per configurazione iniziale
- [x] Scan reti WiFi (fix applicato per MicroPython `decode()`)
- [x] Connessione a rete WiFi
- [x] Salvataggio credenziali in NVS
- [x] Web server HTTP async
- [x] Web GUI control panel (`index.html`)
- [x] Discovery UDP Alpaca (porta 32227)
- [x] Registrazione route Alpaca dopo connessione WiFi
- [x] API Alpaca base (connected, position, ismoving, move, halt, etc.)
- [x] **NUOVO: Modalità Simulator** - funziona senza hardware Robofocus
- [x] **NUOVO: Toggle Serial/Simulator** nella GUI
- [x] **NUOVO: Navigazione post-WiFi** - link al nuovo IP dopo connessione
- [x] **NUOVO: Pagina LOGS** - visualizza log di sistema in tempo reale

## TODO - Problemi da Risolvere

### 1. Test con NINA
**Priorità: Alta**

Verificare che NINA riesca a:
1. Vedere il dispositivo via Alpaca Discovery
2. Connettersi al focuser (in modalità Simulator)
3. Leggere posizione e temperatura
4. Muovere il focuser

**Test da fare:**
1. Avviare ESP32 connesso a WiFi
2. Aprire NINA → Equipment → Focuser
3. Cercare dispositivi Alpaca
4. Connettere e testare movimenti

---

### 2. Test modalità Hardware
**Priorità: Media**

Quando disponibile hardware Robofocus:
1. Collegare ESP32 via TTL 3.3V (con level shifter se necessario)
2. Selezionare "Hardware" nella GUI
3. Verificare comunicazione seriale
4. Testare movimenti reali

---

## Nuove Funzionalità Aggiunte

### Modalità Simulator
- File: `simulator.py`
- Simula posizione focuser (default 30000)
- Simula temperatura con rumore (18°C ± 0.5°C)
- Simula movimento con velocità configurabile
- Permette test senza hardware

### Toggle Serial/Simulator
- GUI: Radio buttons in sezione "Mode & Connection"
- API: `PUT /gui/mode` con `{"use_simulator": true/false}`
- Persiste la scelta in NVS

### Pagina LOGS
- File: `static/logs.html`
- API: `GET /gui/logs`, `DELETE /gui/logs`
- Buffer circolare in memoria (100 entries)
- Auto-refresh opzionale

### Navigazione migliorata
- Header con link a tutte le pagine
- Dopo connessione WiFi: mostra nuovo IP con link cliccabile

---

## Come Deployare su ESP32

```bash
# Requisiti: mpremote installato
pip install mpremote

# Upload tutti i file Python
python -m mpremote connect COM1 cp esp32/*.py :/

# Upload file statici
python -m mpremote connect COM1 mkdir /static
python -m mpremote connect COM1 cp esp32/static/*.html :/static/

# Reset ESP32
python -m mpremote connect COM1 reset

# Monitor seriale
python -m mpremote connect COM1 repl
```

## Struttura API Alpaca

### Management (Discovery)
- `GET /management/apiversions` → `{"Value": [1]}`
- `GET /management/v1/description` → info server
- `GET /management/v1/configureddevices` → lista dispositivi

### Focuser API
- `GET /api/v1/focuser/0/connected` → stato connessione
- `PUT /api/v1/focuser/0/connected` → connetti/disconnetti
- `GET /api/v1/focuser/0/position` → posizione attuale
- `PUT /api/v1/focuser/0/move` → muovi a posizione
- `PUT /api/v1/focuser/0/halt` → ferma movimento
- `GET /api/v1/focuser/0/ismoving` → sta muovendo?
- `GET /api/v1/focuser/0/temperature` → temperatura

### GUI API
- `GET /gui/status` → stato completo (include mode)
- `GET /gui/mode` → modalità corrente
- `PUT /gui/mode` → cambia modalità
- `POST /gui/connect` → connetti focuser
- `POST /gui/disconnect` → disconnetti
- `POST /gui/move` → muovi
- `POST /gui/halt` → ferma
- `GET /gui/logs` → log di sistema
- `DELETE /gui/logs` → pulisci log

---

## Note per il Prossimo Sviluppatore

1. **MicroPython != Python**: alcune funzioni standard non esistono o hanno signature diverse
2. **Memoria limitata**: ESP32 ha ~200KB RAM libera, evitare operazioni pesanti
3. **Async**: tutto il codice usa `uasyncio`, non bloccare mai il loop
4. **NVS errors**: `ESP_ERR_NVS_NOT_FOUND` è normale se config non esiste ancora
5. **COM port**: su Windows la porta seriale potrebbe essere bloccata da altri programmi
6. **Simulator default**: per default parte in modalità simulator (nessun hardware richiesto)
