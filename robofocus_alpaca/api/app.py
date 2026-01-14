"""
FastAPI application factory.
"""

import logging
import itertools
import threading
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel

from robofocus_alpaca.config.models import AppConfig
from robofocus_alpaca.api.models import make_response
from robofocus_alpaca.protocol.port_scanner import list_available_ports, scan_for_robofocus


logger = logging.getLogger(__name__)

# Global server transaction ID counter (thread-safe)
_transaction_counter = itertools.count(1)
_transaction_lock = threading.Lock()


def get_next_transaction_id() -> int:
    """
    Get next server transaction ID (thread-safe).

    Returns:
        Incremented transaction ID.
    """
    with _transaction_lock:
        return next(_transaction_counter)


def create_app(config: AppConfig) -> FastAPI:
    """
    Create FastAPI application instance.

    Args:
        config: Application configuration.

    Returns:
        Configured FastAPI app.
    """
    app = FastAPI(
        title="Robofocus ASCOM Alpaca Driver",
        description="ASCOM Alpaca v1 driver for Robofocus electronic focuser",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # CORS middleware (allow all origins for Alpaca compatibility)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Catch all unhandled exceptions and return Alpaca error response."""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)

        # Try to extract ClientTransactionID from query params or form data
        client_id = 0
        try:
            if request.method == "GET":
                client_id = int(request.query_params.get("ClientTransactionID", 0))
            elif request.method == "PUT":
                form_data = await request.form()
                client_id = int(form_data.get("ClientTransactionID", 0))
        except (ValueError, TypeError):
            pass

        response = make_response(
            value=None,
            client_id=client_id,
            server_id=get_next_transaction_id(),
            error=exc
        )

        return JSONResponse(
            status_code=200,  # Alpaca always returns 200
            content=response.model_dump()
        )

    # Management API endpoints (required for NINA discovery)
    @app.get("/management/apiversions")
    async def get_api_versions():
        """Return supported Alpaca API versions."""
        return {"Value": [1]}

    @app.get("/management/v1/configureddevices")
    async def get_configured_devices():
        """Return list of configured devices."""
        return {
            "Value": [
                {
                    "DeviceName": "Robofocus",
                    "DeviceType": "Focuser",
                    "DeviceNumber": 0,
                    "UniqueID": "robofocus-alpaca-0"
                }
            ]
        }

    @app.get("/management/v1/description")
    async def get_server_description():
        """Return server description."""
        return {
            "Value": {
                "ServerName": "Robofocus Alpaca Driver",
                "Manufacturer": "Custom",
                "ManufacturerVersion": "1.0.0",
                "Location": "localhost"
            }
        }

    # Port management endpoints
    @app.get("/api/v1/management/ports")
    async def get_available_ports():
        """List all available COM ports on the system."""
        ports = list_available_ports(include_bluetooth=True)
        return {
            "Value": [p.to_dict() for p in ports]
        }

    @app.post("/api/v1/management/scan")
    async def scan_ports(request: Request):
        """Scan all COM ports to find Robofocus devices."""
        # Get current port if connected (to skip)
        skip_ports = []
        focuser = getattr(request.app.state, 'focuser', None)
        current_port = None
        if focuser and hasattr(focuser, '_protocol'):
            protocol = focuser._protocol
            if hasattr(protocol, 'port_name') and protocol.is_connected():
                current_port = protocol.port_name
                skip_ports.append(current_port)

        start_time = time.time()
        devices = scan_for_robofocus(
            timeout_seconds=config.serial.scan_timeout_seconds,
            skip_ports=skip_ports,
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        return {
            "Value": [d.to_dict() for d in devices],
            "scan_duration_ms": elapsed_ms,
            "current_port": current_port,
        }

    class SelectPortRequest(BaseModel):
        port: str

    @app.put("/api/v1/management/select-port")
    async def select_port(request: Request, body: SelectPortRequest):
        """Select a COM port to connect to."""
        # This endpoint allows runtime port selection
        # For now, just validate the port exists and has a Robofocus
        devices = scan_for_robofocus(
            timeout_seconds=config.serial.scan_timeout_seconds,
        )

        for device in devices:
            if device.port == body.port:
                # Store selected port for use
                request.app.state.selected_port = body.port
                return {
                    "selected": body.port,
                    "firmware_version": device.firmware_version,
                }

        raise HTTPException(
            status_code=400,
            detail=f"Port {body.port} not found or not a Robofocus device"
        )

    # ASCOM Alpaca Setup Page
    @app.get("/setup/v1/focuser/0/setup", response_class=HTMLResponse)
    async def focuser_setup_page(request: Request):
        """ASCOM Alpaca setup page for focuser configuration."""
        focuser = getattr(request.app.state, 'focuser', None)
        simulator = getattr(request.app.state, 'simulator', None)

        mode = "Simulator" if simulator else "Hardware"
        connected = focuser.connected if focuser else False
        current_port = ""
        firmware = "--"
        position = 0

        if focuser and connected:
            if hasattr(focuser.protocol, 'port_name'):
                current_port = focuser.protocol.port_name or ""
            if hasattr(focuser.protocol, 'firmware_version'):
                firmware = focuser.protocol.firmware_version or "--"
            try:
                position = focuser.get_position()
            except:
                pass

        # Build setup page HTML
        mode_class = 'mode-simulator' if simulator else 'mode-hardware'
        status_class = 'status-connected' if connected else 'status-disconnected'
        status_text = 'Connected' if connected else 'Disconnected'
        port_section_style = 'display:none' if simulator else ''
        connect_disabled = 'disabled' if connected else ''
        disconnect_disabled = '' if connected else 'disabled'

        html = _get_setup_page_html(
            mode, mode_class, status_class, status_text,
            current_port, firmware, position,
            port_section_style, connect_disabled, disconnect_disabled
        )
        return HTMLResponse(content=html)

    logger.info("FastAPI application created")
    return app


def _get_setup_page_html(
    mode, mode_class, status_class, status_text,
    current_port, firmware, position,
    port_section_style, connect_disabled, disconnect_disabled
) -> str:
    """Generate setup page HTML."""
    return f'''<!DOCTYPE html>
<html>
<head>
    <title>Robofocus Driver Setup</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Segoe UI', Tahoma, sans-serif;
            max-width: 600px;
            margin: 40px auto;
            padding: 20px;
            background: #1a1a2e;
            color: #eee;
        }}
        h1 {{ color: #4CAF50; margin-bottom: 5px; }}
        .subtitle {{ color: #888; margin-bottom: 20px; }}
        .section {{
            background: #16213e;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        .section h2 {{
            color: #4CAF50;
            font-size: 1em;
            margin-bottom: 15px;
            border-bottom: 1px solid #4CAF50;
            padding-bottom: 5px;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #333;
        }}
        .info-row:last-child {{ border-bottom: none; }}
        .info-label {{ color: #aaa; }}
        .info-value {{ font-weight: bold; }}
        .status-connected {{ color: #4CAF50; }}
        .status-disconnected {{ color: #f44336; }}
        .mode-simulator {{ color: #9C27B0; }}
        .mode-hardware {{ color: #2196F3; }}
        select, button {{
            padding: 10px 15px;
            font-size: 1em;
            border: none;
            border-radius: 5px;
            margin: 5px 0;
        }}
        select {{ background: #0f3460; color: #eee; width: 100%; }}
        button {{
            background: #4CAF50;
            color: white;
            cursor: pointer;
            width: 100%;
        }}
        button:hover {{ background: #45a049; }}
        button:disabled {{ background: #666; cursor: not-allowed; }}
        .btn-scan {{ background: #2196F3; }}
        .btn-scan:hover {{ background: #1976D2; }}
        .btn-disconnect {{ background: #f44336; }}
        .btn-disconnect:hover {{ background: #d32f2f; }}
        .port-row {{ display: flex; gap: 10px; align-items: center; }}
        .port-row select {{ flex: 1; }}
        .port-row button {{ width: auto; }}
        #status-msg {{
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
            display: none;
        }}
        .msg-success {{ background: #1b5e20; display: block !important; }}
        .msg-error {{ background: #b71c1c; display: block !important; }}
        .msg-info {{ background: #0d47a1; display: block !important; }}
        .link-row {{ text-align: center; margin-top: 20px; }}
        .link-row a {{ color: #4CAF50; text-decoration: none; }}
        .link-row a:hover {{ text-decoration: underline; }}
        .mode-selector {{
            display: flex;
            gap: 10px;
            margin-top: 10px;
        }}
        .mode-option {{
            flex: 1;
            padding: 12px;
            text-align: center;
            border: 2px solid #0f3460;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .mode-option:hover:not(.disabled) {{
            border-color: #4CAF50;
            background: #0f3460;
        }}
        .mode-option.active {{
            border-color: #4CAF50;
            background: #0f3460;
        }}
        .mode-option.disabled {{
            opacity: 0.4;
            cursor: not-allowed;
        }}
        .mode-hint {{
            color: #888;
            font-size: 0.85em;
            margin-top: 8px;
        }}
    </style>
</head>
<body>
    <h1>Robofocus Driver Setup</h1>
    <p class="subtitle">ASCOM Alpaca Driver Configuration</p>

    <div class="section">
        <h2>Current Status</h2>
        <div class="info-row">
            <span class="info-label">Mode:</span>
            <span class="info-value {mode_class}">{mode}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Status:</span>
            <span class="info-value {status_class}">{status_text}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Port:</span>
            <span class="info-value">{current_port or '--'}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Firmware:</span>
            <span class="info-value">{firmware}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Position:</span>
            <span class="info-value">{position}</span>
        </div>
    </div>

    <div class="section">
        <h2>Mode Selection</h2>
        <div class="mode-selector">
            <div class="mode-option" id="mode-hardware" onclick="selectMode(false)">
                <strong>Hardware</strong>
                <div class="mode-hint">Real Robofocus device</div>
            </div>
            <div class="mode-option" id="mode-simulator" onclick="selectMode(true)">
                <strong>Simulator</strong>
                <div class="mode-hint">Virtual device for testing</div>
            </div>
        </div>
        <div id="mode-msg" style="display:none; padding:10px; border-radius:5px; margin-top:10px;"></div>
    </div>

    <div class="section" id="port-section" style="{port_section_style}">
        <h2>COM Port Selection</h2>
        <div class="port-row">
            <select id="port-select">
                <option value="">-- Select Port --</option>
            </select>
            <button class="btn-scan" onclick="scanPorts()">Scan</button>
        </div>
        <button onclick="connectPort()" id="btn-connect" {connect_disabled}>Connect</button>
        <button class="btn-disconnect" onclick="disconnectPort()" id="btn-disconnect" {disconnect_disabled}>Disconnect</button>
        <div id="status-msg"></div>
    </div>

    <div class="link-row">
        <a href="/">Open Full Control Panel</a>
    </div>

    <script>
        async function scanPorts() {{
            var select = document.getElementById('port-select');
            var msg = document.getElementById('status-msg');

            msg.className = 'msg-info';
            msg.textContent = 'Scanning ports...';

            try {{
                var response = await fetch('/gui/scan', {{ method: 'POST' }});
                var devices = await response.json();

                // Clear existing options
                while (select.options.length > 1) select.remove(1);

                if (devices.length === 0) {{
                    msg.className = 'msg-error';
                    msg.textContent = 'No Robofocus devices found';
                    return;
                }}

                for (var i = 0; i < devices.length; i++) {{
                    var d = devices[i];
                    var opt = document.createElement('option');
                    opt.value = d.port;
                    opt.textContent = d.port + ' - ' + d.description + ' (FW: ' + d.firmware_version + ')';
                    select.appendChild(opt);
                }}

                msg.className = 'msg-success';
                msg.textContent = 'Found ' + devices.length + ' device(s)';

            }} catch (e) {{
                msg.className = 'msg-error';
                msg.textContent = 'Scan failed: ' + e.message;
            }}
        }}

        async function connectPort() {{
            var port = document.getElementById('port-select').value;
            var msg = document.getElementById('status-msg');

            if (!port) {{
                msg.className = 'msg-error';
                msg.textContent = 'Please select a port first';
                return;
            }}

            msg.className = 'msg-info';
            msg.textContent = 'Connecting to ' + port + '...';

            try {{
                var response = await fetch('/gui/connect', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ port: port }})
                }});

                if (response.ok) {{
                    msg.className = 'msg-success';
                    msg.textContent = 'Connected successfully!';
                    setTimeout(function() {{ location.reload(); }}, 1000);
                }} else {{
                    var err = await response.json();
                    msg.className = 'msg-error';
                    msg.textContent = err.detail || 'Connection failed';
                }}
            }} catch (e) {{
                msg.className = 'msg-error';
                msg.textContent = 'Connection failed: ' + e.message;
            }}
        }}

        async function disconnectPort() {{
            var msg = document.getElementById('status-msg');

            try {{
                var response = await fetch('/gui/disconnect', {{ method: 'POST' }});
                if (response.ok) {{
                    msg.className = 'msg-success';
                    msg.textContent = 'Disconnected';
                    setTimeout(function() {{ location.reload(); }}, 1000);
                }}
            }} catch (e) {{
                msg.className = 'msg-error';
                msg.textContent = 'Disconnect failed: ' + e.message;
            }}
        }}

        // Mode selection functions
        async function loadCurrentMode() {{
            try {{
                var response = await fetch('/gui/mode');
                var data = await response.json();

                // Update UI based on current mode
                var hwOption = document.getElementById('mode-hardware');
                var simOption = document.getElementById('mode-simulator');

                if (data.current_mode === 'simulator') {{
                    simOption.classList.add('active');
                    hwOption.classList.remove('active');
                }} else {{
                    hwOption.classList.add('active');
                    simOption.classList.remove('active');
                }}

                // Disable mode selection if connected
                if (!data.can_switch) {{
                    hwOption.classList.add('disabled');
                    simOption.classList.add('disabled');
                    hwOption.onclick = null;
                    simOption.onclick = null;
                }}
            }} catch (e) {{
                console.error('Failed to load mode:', e);
            }}
        }}

        async function selectMode(useSimulator) {{
            var modeMsg = document.getElementById('mode-msg');

            try {{
                var response = await fetch('/gui/mode');
                var data = await response.json();

                // Check if switching is allowed
                if (!data.can_switch) {{
                    modeMsg.style.display = 'block';
                    modeMsg.style.background = '#b71c1c';
                    modeMsg.textContent = data.reason || 'Cannot switch mode while connected';
                    return;
                }}

                // Perform mode switch
                modeMsg.style.display = 'block';
                modeMsg.style.background = '#0d47a1';
                modeMsg.textContent = 'Switching mode...';

                var switchResponse = await fetch('/gui/mode', {{
                    method: 'PUT',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ use_simulator: useSimulator }})
                }});

                if (switchResponse.ok) {{
                    var result = await switchResponse.json();
                    modeMsg.style.background = '#1b5e20';
                    modeMsg.textContent = result.message + ' - Reloading...';
                    setTimeout(function() {{ location.reload(); }}, 1500);
                }} else {{
                    var err = await switchResponse.json();
                    modeMsg.style.background = '#b71c1c';
                    modeMsg.textContent = err.detail || 'Mode switch failed';
                }}
            }} catch (e) {{
                modeMsg.style.display = 'block';
                modeMsg.style.background = '#b71c1c';
                modeMsg.textContent = 'Mode switch failed: ' + e.message;
            }}
        }}

        // Load ports on page load
        async function loadPorts() {{
            try {{
                var response = await fetch('/gui/ports');
                var ports = await response.json();
                var select = document.getElementById('port-select');

                for (var i = 0; i < ports.length; i++) {{
                    var p = ports[i];
                    var opt = document.createElement('option');
                    opt.value = p.name;
                    opt.textContent = p.name + ' - ' + p.description;
                    select.appendChild(opt);
                }}
            }} catch (e) {{
                console.error('Failed to load ports:', e);
            }}
        }}

        // Load initial state
        loadCurrentMode();
        loadPorts();
    </script>
</body>
</html>'''
