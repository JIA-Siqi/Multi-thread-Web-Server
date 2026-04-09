#!/usr/bin/env python3
"""
A multi-threaded HTTP/1.1 web server that handles:
- GET and HEAD requests for text and image files
- Persistent (keep-alive) and non-persistent (close) connections
- 5 HTTP status codes: 200, 304, 400, 403, 404
- Last-Modified and If-Modified-Since headers
- Concurrent client handling via threading
- Request logging to file

Usage:
    python server.py              # Uses current directory as document root
    python server.py test_files   # Uses 'test_files' folder as document root
    python server.py /path/to/files  # Uses custom path as document root
"""

import socket
import threading
import os
import sys
import datetime
import mimetypes
from email.utils import parsedate_to_datetime, formatdate
from urllib.parse import unquote

# ==================== CONFIGURATION ====================
HOST = '127.0.0.1'      # Localhost only (change to '0.0.0.0' for network access)
PORT = 8080             # Non-privileged port (not 80 to avoid conflicts)
LOG_FILE = "../server.log" # Log file in parent folder (parallel to src and test_files)

# HTTP status codes and their messages (RFC 7231 compliant)
STATUS_MESSAGES = {
    "200": "200 OK",
    "304": "304 Not Modified",
    "400": "400 Bad Request",
    "403": "403 Forbidden",
    "404": "404 Not Found"
}

# ==================== DOCUMENT ROOT CONFIGURATION ====================

def set_document_root():
    """
    Set the document root directory based on command line argument.
    Usage: python server.py [document_root_path]
    
    If no argument is provided, uses current directory.
    If argument is provided, changes to that directory if it exists.
    """
    if len(sys.argv) > 1:
        doc_root = sys.argv[1]
        if os.path.exists(doc_root) and os.path.isdir(doc_root):
            os.chdir(doc_root)
            print(f"[CONFIG] Using document root: {os.path.abspath('.')}")
            return True
        else:
            print(f"[WARNING] Directory '{doc_root}' not found!")
            print(f"[WARNING] Using current directory instead: {os.path.abspath('.')}")
            return False
    else:
        print(f"[CONFIG] Using current directory as document root: {os.path.abspath('.')}")
        return True

# ==================== LOGGING FUNCTIONS ====================

def log_request(client_address, request_file, status_code):
    """
    Record client request statistics to log file.
    Format: client_IP, timestamp, requested_file, status_code
    
    Requirements:
    - Client hostname/IP address
    - Access time
    - Requested file name
    - Response type/status code
    """
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{client_address[0]}, {timestamp}, {request_file}, {status_code}\n"
    
    # Append to log file (creates file if doesn't exist)
    with open(LOG_FILE, "a") as f:
        f.write(log_entry)

# ==================== FILE AND HEADER HELPERS ====================

def get_last_modified(filepath):
    """
    Get file's last modification time in HTTP format (RFC 1123).
    Example: "Tue, 31 Mar 2026 10:00:00 GMT"
    """
    mtime = os.path.getmtime(filepath)
    return formatdate(mtime, usegmt=True)

def parse_http_date(date_string):
    """
    Parse HTTP date string to Unix timestamp for comparison.
    Returns None if parsing fails (server should ignore invalid dates).
    """
    try:
        return parsedate_to_datetime(date_string).timestamp()
    except (ValueError, TypeError):
        return None

def get_error_body(status_code):
    """
    Generate HTML error response body for client-friendly error pages.
    Returns appropriate HTML for 400, 403, 404 status codes.
    """
    error_pages = {
        "400": """<!DOCTYPE html>
<html>
<head><title>400 Bad Request</title></head>
<body>
    <h1>400 Bad Request</h1>
    <p>The server could not understand the request due to invalid syntax.</p>
    <hr><em>COMP2322 Multi-thread Web Server</em>
</body>
</html>""",
        "403": """<!DOCTYPE html>
<html>
<head><title>403 Forbidden</title></head>
<body>
    <h1>403 Forbidden</h1>
    <p>You don't have permission to access this resource.</p>
    <hr><em>COMP2322 Multi-thread Web Server</em>
</body>
</html>""",
        "404": """<!DOCTYPE html>
<html>
<head><title>404 Not Found</title></head>
<body>
    <h1>404 Not Found</h1>
    <p>The requested file was not found on this server.</p>
    <hr><em>COMP2322 Multi-thread Web Server</em>
</body>
</html>"""
    }
    return error_pages.get(status_code, "<html><body><h1>Error</h1></body></html>")

def is_path_safe(filepath):
    """
    Security: Prevent directory traversal attacks.
    Ensures requested path stays within server's document root.
    """
    abs_path = os.path.abspath(filepath)
    current_dir = os.path.abspath('.')
    return abs_path.startswith(current_dir)

# ==================== RESPONSE GENERATION ====================

def send_response(sock, status_code, headers=None, body=None, keep_alive=False):
    """
    Send HTTP response with proper headers and optional body.
    
    Args:
        sock: Client socket connection
        status_code: HTTP status code (e.g., "200", "404")
        headers: Dict of additional headers to include
        body: Response body (string or bytes)
        keep_alive: Whether to keep connection open
    """
    # Status line: HTTP/1.1 200 OK
    status_line = f"HTTP/1.1 {STATUS_MESSAGES[status_code]}\r\n"
    
    # Required response headers
    response_headers = {
        'Connection': 'keep-alive' if keep_alive else 'close',
        'Date': formatdate(usegmt=True)
    }
    
    if headers:
        response_headers.update(headers)
    
    # Build header string
    header_string = status_line
    for key, value in response_headers.items():
        header_string += f"{key}: {value}\r\n"
    header_string += "\r\n"  # Blank line separates headers from body
    
    # Send headers
    sock.send(header_string.encode())
    
    # Send body if present (for GET responses or error pages)
    if body:
        if isinstance(body, str):
            body = body.encode()
        sock.send(body)
    
    return keep_alive

# ==================== REQUEST PROCESSING ====================

def process_request(sock, method, filename, headers, client_addr, http_version):
    """
    Process validated GET/HEAD requests.
    Handles file serving, caching headers, and connection persistence.
    
    Requirements handled:
    - GET for text/image files
    - HEAD command
    - Last-Modified/If-Modified-Since
    - Connection persistence
    """
    
    # Get file metadata
    file_mtime = os.path.getmtime(filename)
    last_modified = get_last_modified(filename)
    
    # Determine content type from file extension
    content_type, _ = mimetypes.guess_type(filename)
    if not content_type:
        content_type = 'application/octet-stream'
    
    # ===== Handle If-Modified-Since (304 Not Modified) =====
    if 'if-modified-since' in headers:
        client_time = parse_http_date(headers['if-modified-since'])
        # If file hasn't changed since client's cached version, return 304
        if client_time is not None and file_mtime <= client_time:
            response_headers = {
                'Last-Modified': last_modified,
                'Content-Type': content_type
            }
            keep_alive = headers.get('connection', '').lower() == 'keep-alive'
            send_response(sock, "304", headers=response_headers, keep_alive=keep_alive)
            log_request(client_addr, filename, "304")
            return keep_alive
    
    # ===== Read file content for GET requests =====
    content = None
    if method == 'GET':
        try:
            with open(filename, 'rb') as f:
                content = f.read()
        except IOError:
            send_response(sock, "404", body=get_error_body("404"))
            log_request(client_addr, filename, "404")
            return False
    
    # Content length: for HEAD we just need the size, for GET we have the content
    if method == 'HEAD':
        content_length = os.path.getsize(filename)
    else:
        content_length = len(content) if content else 0
    
    # ===== Determine connection persistence =====
    # HTTP/1.1 defaults to persistent (keep-alive)
    # HTTP/1.0 defaults to non-persistent (close)
    connection_header = headers.get('connection', '').lower()
    if http_version == 'HTTP/1.1':
        keep_alive = connection_header != 'close'
    else:  # HTTP/1.0
        keep_alive = connection_header == 'keep-alive'
    
    # ===== Build and send 200 OK response =====
    response_headers = {
        'Content-Type': content_type,
        'Content-Length': str(content_length),
        'Last-Modified': last_modified,
        'Server': 'COMP2322-WebServer/1.0'
    }
    
    send_response(sock, "200", headers=response_headers,
                 body=content if method == 'GET' else None,
                 keep_alive=keep_alive)
    
    log_request(client_addr, filename, "200")
    return keep_alive

# ==================== CLIENT HANDLER ====================

def handle_client(connection_socket, client_address):
    """
    Handle individual client connection in a separate thread.
    Supports persistent connections (multiple requests per connection).
    
    Requirement: Multi-threaded server
    """
    keep_alive = True
    
    try:
        while keep_alive:
            # Set timeout to detect dead connections
            connection_socket.settimeout(5.0)
            
            try:
                # Receive HTTP request (max 4096 bytes)
                request = connection_socket.recv(4096).decode()
                if not request:
                    break
                
                # Parse request into lines
                lines = request.split('\r\n')
                if len(lines) < 1:
                    break
                
                # ===== Parse request line: METHOD PATH VERSION =====
                request_line = lines[0].split()
                if len(request_line) != 3:
                    send_response(connection_socket, "400", body=get_error_body("400"))
                    log_request(client_address, "Invalid Request", "400")
                    break
                
                method, path, http_version = request_line
                
                # Validate HTTP version
                if http_version not in ['HTTP/1.0', 'HTTP/1.1']:
                    send_response(connection_socket, "400", body=get_error_body("400"))
                    log_request(client_address, path, "400")
                    break
                
                # Decode URL and sanitize path
                path = unquote(path)
                filename = path.lstrip('/')
                if not filename:  # Default to index.html for root path
                    filename = 'index.html'
                
                # Security: Prevent directory traversal
                if not is_path_safe(filename):
                    send_response(connection_socket, "403", body=get_error_body("403"))
                    log_request(client_address, filename, "403")
                    break
                
                # ===== Parse request headers (case-insensitive) =====
                headers = {}
                for line in lines[1:]:
                    if ': ' in line:
                        key, value = line.split(": ", 1)
                        headers[key.lower()] = value  # Store in lowercase for case-insensitive lookup
                
                # ===== Check if file exists =====
                if not os.path.exists(filename):
                    send_response(connection_socket, "404", body=get_error_body("404"))
                    log_request(client_address, filename, "404")
                    keep_alive = headers.get('connection', '').lower() == 'keep-alive'
                    continue
                
                # ===== Forbidden files check =====
                # Block hidden files and potentially dangerous extensions
                forbidden_extensions = ('.pyc', '.pyo', '.exe', '.dll', '.conf')
                if filename.endswith(forbidden_extensions) or filename.startswith('.'):
                    send_response(connection_socket, "403", body=get_error_body("403"))
                    log_request(client_address, filename, "403")
                    keep_alive = headers.get('connection', '').lower() == 'keep-alive'
                    continue
                
                # ===== Validate HTTP method =====
                # Only GET and HEAD are supported
                if method not in ['GET', 'HEAD']:
                    send_response(connection_socket, "400", body=get_error_body("400"))
                    log_request(client_address, filename, "400")
                    keep_alive = headers.get('connection', '').lower() == 'keep-alive'
                    continue
                
                # Process the validated request
                keep_alive = process_request(connection_socket, method, filename,
                                            headers, client_address, http_version)
                
            except socket.timeout:
                # No more data, close connection
                break
            except Exception as e:
                print(f"[ERROR] Processing request from {client_address}: {e}")
                break
                
    finally:
        connection_socket.close()

# ==================== SERVER LAUNCHER ====================

def start_server():
    """
    Initialize server socket, bind to port, and start listening.
    Creates a new thread for each incoming connection.
    """
    # Set document root from command line argument
    set_document_root()
    
    # Create TCP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Allow port reuse (helps with quick restarts)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Bind to host and port
    server_socket.bind((HOST, PORT))
    
    # Start listening (backlog of 10 pending connections)
    server_socket.listen(10)
    
    print("=" * 60)
    print("COMP 2322 - Multi-thread Web Server")
    print("=" * 60)
    print(f"Server running on: http://{HOST}:{PORT}")
    print(f"Log file: {LOG_FILE}")
    print(f"Document root: {os.path.abspath('.')}")
    print("Supported methods: GET, HEAD")
    print("Supported status codes: 200, 304, 400, 403, 404")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    
    # Check if index.html exists in document root
    if not os.path.exists('index.html'):
        print("\n[WARNING] No index.html found in document root!")
        print("You can:")
        print("  1. Create an index.html file in this directory")
        print("  2. Run with: python server.py test_files")
        print("  3. Run with: python server.py /path/to/your/files\n")
    
    try:
        while True:
            # Accept new connection (blocks until a client connects)
            connection_socket, client_address = server_socket.accept()
            print(f"[CONNECTION] {client_address[0]}:{client_address[1]}")
            
            # Create and start a new thread for this client
            client_thread = threading.Thread(
                target=handle_client,
                args=(connection_socket, client_address)
            )
            client_thread.daemon = True  # Thread exits when main thread exits
            client_thread.start()
            
    except KeyboardInterrupt:
        print("\n\n[SHUTDOWN] Received interrupt signal...")
    finally:
        server_socket.close()
        print("[SHUTDOWN] Server stopped.")

# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    start_server()