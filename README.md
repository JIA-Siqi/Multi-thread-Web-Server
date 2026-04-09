## Multi-thread Web Server

A production-ready, multi-threaded HTTP/1.1 web server built from scratch using Python sockets. Implements full HTTP protocol semantics including persistent connections, conditional requests, and comprehensive logging.

## Features

- **Multi-threaded Architecture** – Each client request handled in a dedicated thread for concurrent processing
- **HTTP/1.1 Compliance** – Supports GET and HEAD methods with proper request/response formatting
- **File Serving** – Serves text files, HTML, JPEG, PNG, and other binary files with correct MIME types
- **Status Codes** – Implements 200 OK, 304 Not Modified, 400 Bad Request, 403 Forbidden, 404 Not Found
- **Conditional Requests** – Last-Modified and If-Modified-Since headers for HTTP caching
- **Connection Management** – Persistent (keep-alive) and non-persistent (close) connections
- **Security** – Path sanitization prevents directory traversal attacks; hidden files return 403
- **Request Logging** – Records client IP, timestamp, requested file, and response status to `server.log`

## Requirements

- Python 3.6 or higher
- No external dependencies (uses only standard library)

## Installation

```bash
git clone https://github.com/JIA-Siqi/web-server.git
cd web-server
```

## Project Structure

```
web-server/
├── src/
│   └── server.py          # Main server implementation
├── test_files/            # Test files for validation
│   ├── index.html
│   ├── test.txt
│   ├── test.jpg
│   ├── test.png
│   └── .hidden_file
├── server.log             # Request log (auto-generated)
└── README.md
```

## Usage

### Start the Server

```bash
# Use test_files as document root (recommended)
python src/server.py test_files

# Use current directory as document root
python src/server.py

# Use custom document root
python src/server.py /path/to/your/files
```

### Expected Output

```
[CONFIG] Using document root: /path/to/test_files
============================================================
COMP 2322 - Multi-thread Web Server
============================================================
Server running on: http://127.0.0.1:8080
Log file: ../server.log
Document root: /path/to/test_files
Supported methods: GET, HEAD
Supported status codes: 200, 304, 400, 403, 404
Press Ctrl+C to stop the server
============================================================
```

### Testing with Browser

| URL | Expected Result |
|-----|-----------------|
| `http://127.0.0.1:8080/` | Homepage (200 OK) |
| `http://127.0.0.1:8080/test.txt` | Text file content |
| `http://127.0.0.1:8080/test.jpg` | JPEG image |
| `http://127.0.0.1:8080/test.png` | PNG image |
| `http://127.0.0.1:8080/missing.html` | 404 Not Found |
| `http://127.0.0.1:8080/.hidden_file` | 403 Forbidden |

### Testing with cURL

```bash
# GET request
curl http://127.0.0.1:8080/index.html

# HEAD request (headers only)
curl -I http://127.0.0.1:8080/index.html

# Conditional GET (returns 304 if not modified)
curl -I -H "If-Modified-Since: Tue, 31 Dec 2030 10:00:00 GMT" http://127.0.0.1:8080/index.html

# Invalid method (returns 400)
curl -X INVALID http://127.0.0.1:8080/

# Connection: close (non-persistent)
curl -v -H "Connection: close" http://127.0.0.1:8080/index.html
```

## Log File Format

Each request generates one log entry:

```
127.0.0.1, 2026-04-09 20:53:21, test.txt, 200
127.0.0.1, 2026-04-09 20:53:49, missing.html, 404
127.0.0.1, 2026-04-09 20:53:58, .hidden_file, 403
127.0.0.1, 2026-04-09 20:54:20, index.html, 304
```

View the log:
```bash
cat server.log      # Linux/macOS
type server.log     # Windows
```

## Stop the Server

Press `Ctrl + C` in the terminal window.

## Technical Details

### Socket Implementation
- TCP socket with `SO_REUSEADDR` for port reuse
- Listens on `127.0.0.1:8080` (configurable)
- 5-second timeout to prevent hanging connections

### Threading Model
- Main thread accepts connections
- Each client gets a dedicated daemon thread
- Supports unlimited concurrent connections

### HTTP Protocol
- RFC 7230/7231 compliant
- Case-insensitive header parsing
- RFC 1123 date format for Last-Modified
- MIME type detection via `mimetypes`

### Security
- `os.path.abspath()` prevents directory traversal
- Hidden files (`.`) return 403 Forbidden
- Blocked extensions: `.pyc`, `.exe`, `.dll`, `.conf`

## Troubleshooting

| Issue                | Solution                                    |
|----------------------|---------------------------------------------|
| Port 8080 in use     | Change `PORT` in `server.py` (line 26)      |
| Connection refused   | Ensure server is running before testing     |
| 404 Not Found        | Verify file exists in document root         |
| Log file not created | Check write permissions in parent directory |

## License

This project was developed for COMP 2322 Computer Networking course.

## Author

JIA Siqi
