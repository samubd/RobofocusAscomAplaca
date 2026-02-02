"""
Lightweight async HTTP server for ESP32.

Provides routing, static file serving, and JSON handling.
"""

import uasyncio as asyncio
import json
import os
import time

# Disable HTTP request logging for performance (print() blocks the event loop)
# Set to True only for debugging
DEBUG_HTTP = False


class Request:
    """HTTP request object."""

    def __init__(self):
        self.method = ""
        self.path = ""
        self.query = {}
        self.headers = {}
        self.body = ""
        self.form_data = {}
        self.json_data = None

    def parse_query_string(self, qs: str):
        """Parse query string into dict."""
        if not qs:
            return
        for pair in qs.split('&'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                # URL decode
                value = value.replace('+', ' ')
                value = self._url_decode(value)
                self.query[key] = value

    def parse_form_data(self, body: str):
        """Parse form-urlencoded body into dict."""
        if not body:
            return
        for pair in body.split('&'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                value = value.replace('+', ' ')
                value = self._url_decode(value)
                self.form_data[key] = value

    def _url_decode(self, s: str) -> str:
        """Simple URL decoding."""
        result = []
        i = 0
        while i < len(s):
            if s[i] == '%' and i + 2 < len(s):
                try:
                    result.append(chr(int(s[i+1:i+3], 16)))
                    i += 3
                    continue
                except ValueError:
                    pass
            result.append(s[i])
            i += 1
        return ''.join(result)


class Response:
    """HTTP response builder."""

    def __init__(self):
        self.status = 200
        self.status_text = "OK"
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.body = ""

    def set_status(self, code: int, text: str = None):
        """Set response status code."""
        self.status = code
        self.status_text = text or self._status_text(code)

    def _status_text(self, code: int) -> str:
        texts = {
            200: "OK",
            201: "Created",
            204: "No Content",
            400: "Bad Request",
            404: "Not Found",
            405: "Method Not Allowed",
            413: "Payload Too Large",
            500: "Internal Server Error"
        }
        return texts.get(code, "Unknown")

    def json(self, data, status: int = 200):
        """Set JSON response body."""
        self.status = status
        self.status_text = self._status_text(status)
        self.headers["Content-Type"] = "application/json"
        self.body = json.dumps(data)
        return self

    def html(self, content: str, status: int = 200):
        """Set HTML response body."""
        self.status = status
        self.status_text = self._status_text(status)
        self.headers["Content-Type"] = "text/html; charset=utf-8"
        self.body = content
        return self

    def text(self, content: str, status: int = 200):
        """Set plain text response body."""
        self.status = status
        self.status_text = self._status_text(status)
        self.headers["Content-Type"] = "text/plain; charset=utf-8"
        self.body = content
        return self

    def error(self, message: str, status: int = 400):
        """Set error response."""
        return self.json({"error": message, "detail": message}, status)

    def build(self) -> bytes:
        """Build HTTP response bytes."""
        lines = [f"HTTP/1.1 {self.status} {self.status_text}"]

        # Add headers
        if self.body:
            self.headers["Content-Length"] = str(len(self.body.encode('utf-8') if isinstance(self.body, str) else self.body))

        for key, value in self.headers.items():
            lines.append(f"{key}: {value}")

        lines.append("")  # Blank line before body

        if self.body:
            lines.append(self.body if isinstance(self.body, str) else self.body.decode())

        return "\r\n".join(lines).encode('utf-8')


class WebServer:
    """
    Lightweight async HTTP server.

    Usage:
        server = WebServer()

        @server.route("/api/status", methods=["GET"])
        async def get_status(request, response):
            return response.json({"status": "ok"})

        await server.start(port=80)
    """

    # Maximum body size in bytes (8KB to prevent OOM on ESP32)
    MAX_BODY_SIZE = 8192

    def __init__(self, static_dir: str = "/static"):
        self._routes = []
        self._static_dir = static_dir
        self._server = None

    def route(self, path: str, methods: list = None):
        """
        Decorator to register a route handler.

        Args:
            path: URL path pattern
            methods: List of HTTP methods (default: ["GET"])
        """
        if methods is None:
            methods = ["GET"]

        def decorator(handler):
            self._routes.append({
                'path': path,
                'methods': methods,
                'handler': handler
            })
            return handler

        return decorator

    def add_route(self, path: str, handler, methods: list = None):
        """Add route programmatically."""
        if methods is None:
            methods = ["GET"]
        self._routes.append({
            'path': path,
            'methods': methods,
            'handler': handler
        })

    def _match_route(self, method: str, path: str):
        """Find matching route handler."""
        for route in self._routes:
            if path == route['path'] and method in route['methods']:
                return route['handler']
        return None

    async def _handle_client(self, reader, writer):
        """Handle incoming HTTP request with Keep-Alive support."""
        keep_alive = True
        request_count = 0
        max_requests = 100  # Max requests per connection

        try:
            while keep_alive and request_count < max_requests:
                request_count += 1

                # Read request line (shorter timeout for keep-alive)
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=30 if request_count == 1 else 5)
                except asyncio.TimeoutError:
                    break  # Connection idle, close it

                if not line:
                    break

                line = line.decode('utf-8').strip()
                if not line:  # Empty line, connection closed
                    break

                parts = line.split(' ')
                if len(parts) < 2:
                    break

                request = Request()
                request.method = parts[0]

                # Log incoming request (disabled by default for performance)
                if DEBUG_HTTP:
                    print(f"[web:{time.ticks_ms()//1000}s] {request.method} {parts[1]}")

                # Parse path and query string
                full_path = parts[1]
                if '?' in full_path:
                    request.path, query_string = full_path.split('?', 1)
                    request.parse_query_string(query_string)
                else:
                    request.path = full_path

                # Read headers
                while True:
                    line = await asyncio.wait_for(reader.readline(), timeout=5)
                    if not line or line == b'\r\n':
                        break
                    line = line.decode('utf-8').strip()
                    if ':' in line:
                        key, value = line.split(':', 1)
                        request.headers[key.strip().lower()] = value.strip()

                # Check if client wants keep-alive
                connection = request.headers.get('connection', '').lower()
                keep_alive = connection != 'close'

                # Read body if present
                content_length = int(request.headers.get('content-length', 0))
                if content_length > 0:
                    if content_length > self.MAX_BODY_SIZE:
                        response = Response()
                        response.error(f"Request body too large", 413)
                        response.headers["Connection"] = "close"
                        writer.write(response.build())
                        await writer.drain()
                        break

                    request.body = (await reader.read(content_length)).decode('utf-8')

                    content_type = request.headers.get('content-type', '')
                    if 'application/json' in content_type:
                        try:
                            request.json_data = json.loads(request.body)
                        except Exception:
                            pass
                    elif 'application/x-www-form-urlencoded' in content_type:
                        request.parse_form_data(request.body)

                # Create response
                response = Response()

                # Add CORS and Keep-Alive headers
                response.headers["Access-Control-Allow-Origin"] = "*"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type"
                if keep_alive:
                    response.headers["Connection"] = "keep-alive"
                    response.headers["Keep-Alive"] = "timeout=5, max=100"
                else:
                    response.headers["Connection"] = "close"

                # Handle OPTIONS preflight
                if request.method == "OPTIONS":
                    response.set_status(204)
                    writer.write(response.build())
                    await writer.drain()
                    continue

                # Try to match route
                handler = self._match_route(request.method, request.path)

                if handler:
                    try:
                        await handler(request, response)
                    except Exception as e:
                        if DEBUG_HTTP:
                            print(f"[web] Err: {e}")
                        response.error(str(e), 500)
                else:
                    if not await self._serve_static(request, response):
                        response.error("Not Found", 404)

                # Send response
                writer.write(response.build())
                await writer.drain()

        except asyncio.TimeoutError:
            pass
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def _serve_static(self, request: Request, response: Response) -> bool:
        """
        Serve static file if it exists.

        Returns:
            True if file served, False otherwise.
        """
        # Clean path
        path = request.path
        if path == "/" or path == "":
            path = "/index.html"

        # Security: prevent directory traversal
        if ".." in path:
            return False

        # Build file path
        file_path = self._static_dir + path

        # Check if file exists
        try:
            stat = os.stat(file_path)
            if stat[0] & 0x4000:  # Is directory
                file_path += "/index.html"
                stat = os.stat(file_path)
        except OSError:
            return False

        # Determine content type
        content_type = "application/octet-stream"
        if file_path.endswith(".html"):
            content_type = "text/html; charset=utf-8"
        elif file_path.endswith(".css"):
            content_type = "text/css"
        elif file_path.endswith(".js"):
            content_type = "application/javascript"
        elif file_path.endswith(".json"):
            content_type = "application/json"
        elif file_path.endswith(".png"):
            content_type = "image/png"
        elif file_path.endswith(".ico"):
            content_type = "image/x-icon"

        # Read and serve file
        try:
            with open(file_path, 'r' if 'text' in content_type or content_type == 'application/javascript' or content_type == 'application/json' else 'rb') as f:
                content = f.read()

            response.status = 200
            response.status_text = "OK"
            response.headers["Content-Type"] = content_type
            response.headers["Cache-Control"] = "max-age=3600"
            response.body = content
            if DEBUG_HTTP:
                print(f"[web] Static {file_path}")
            return True

        except Exception:
            return False

    async def start(self, host: str = "0.0.0.0", port: int = 80):
        """
        Start the HTTP server.

        Args:
            host: Bind address (default: all interfaces)
            port: Listen port (default: 80)
        """
        print(f"[web] Starting server on {host}:{port}")
        self._server = await asyncio.start_server(
            self._handle_client,
            host,
            port
        )
        print(f"[web] Server running on http://{host}:{port}")

    async def stop(self):
        """Stop the HTTP server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            print("[web] Server stopped")


# Global server instance
server = WebServer()
