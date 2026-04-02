# CAT Printer Web Interface

A full-featured web interface for CAT thermal printers with Flask, Vue.js, and Docker support. Based on [go-catprinter](https://git.boxo.cc/massivebox/go-catprinter).

![CAT Printer](https://img.shields.io/badge/CAT-Thermal-Printer-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue)

## Features

### Core Features
- **Keep-Alive System**: Automatically pings the printer every 2.5 minutes to prevent auto shut-off
- **Auto-Reconnect**: Automatically reconnects when the printer disconnects
- **Multi-Copy Support**: Print up to 10 copies of any content
- **Job Queue**: Background processing of print jobs

### Printing Options
- **Task Lists**: Create and print organized task lists with titles and deadlines
- **Text Notes**: Print free-form text with automatic wrapping
- **Images**: Print photos with optional rotation (90° increments)
- **PDF**: Print PDF documents (requires PyMuPDF)

### Security
- **Password Protection**: Optional Basic Auth for web interface
- **Configurable via Environment Variables**: Easy deployment configuration

### Deployment
- **Docker Compose**: Full containerized deployment
- **Bluetooth LE Support**: Native BLE support via go-catprinter

## Quick Start

### Prerequisites

1. A CAT thermal printer (model supported by go-catprinter)
2. Python 3.11+ or Docker
3. Bluetooth adapter

### Option 1: Docker Compose (Recommended)

```bash
# 1. Clone and configure
git clone https://github.com/yourusername/go-catprinter-web.git
cd go-catprinter-web

# 2. Copy environment template
cp .env.example .env

# 3. Build and run
docker-compose up --build

# 4. Access at http://localhost:5000
```

### Option 2: Python Virtual Environment

```bash
# 1. Install system dependencies
sudo apt install bluetooth libbluetooth-dev libglib2.0-dev fonts-dejavu-core

# 2. Clone and configure
git clone https://github.com/yourusername/go-catprinter-web.git
cd go-catprinter-web

# 3. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# 6. Run
python app.py
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|------------|---------|
| `CAT_PRINTER_MAC` | MAC address of your printer | `A1:49:35:A0:C8:79` |
| `PRINTER_WORKDIR` | Working directory for print jobs | `/app/catprinter` |
| `PING_INTERVAL` | Keep-alive ping interval (seconds) | `150` |
| `FLASK_PORT` | Port for web server | `5000` |
| `ENABLE_AUTH` | Enable password protection | `false` |
| `ADMIN_USER` | Admin username | `admin` |
| `ADMIN_PASSWORD` | Admin password | `changeme` |

### Building the catprinter CLI

If not using Docker, build the Go CLI:

```bash
cd go-catprinter
go build -o catprinter ./cli
# This creates the 'catprinter' binary used by the Flask app
```

## API Endpoints

### Public
- `GET /api/health` - Health check

### Protected (with authentication)
- `GET /` - Web interface
- `GET /api/tareas` - Get task list
- `POST /api/tareas` - Save task list
- `POST /api/imprimir/tareas` - Print task list
- `POST /api/imprimir/texto` - Print text
- `POST /api/imprimir/imagen` - Print image
- `POST /api/imprimir/pdf` - Print PDF
- `GET /api/status` - Get printer status
- `POST /api/keepalive/start` - Start keep-alive
- `POST /api/keepalive/stop` - Stop keep-alive
- `POST /api/reconnect` - Force reconnection

## Supported Printers

This project uses [go-catprinter](https://git.boxo.cc/massivebox/go-catprinter) which supports various CAT thermal printers. Check their documentation for the complete list.

Known compatible printers:
- CAT PRT-01WE
- Various unnamed CAT thermal printers

## Project Structure

```
go-catprinter-web/
├── app.py                 # Flask API server
├── templates/
│   └── index.html       # Vue.js web interface
├── Dockerfile           # Docker image definition
├── docker-compose.yml   # Docker Compose setup
├── requirements.txt    # Python dependencies
├── .env.example     # Environment template
└── README.md        # This file
```

## Troubleshooting

### Printer Not Found
- Make sure Bluetooth is enabled: `sudo systemctl enable bluetooth`
- Check printer is powered on and in range
- Verify MAC address is correct

### Connection Errors
- The printer may have turned off - use the keep-alive feature to prevent this
- Try manually reconnecting: `POST /api/reconnect`

### Print Quality Issues
- Try with and without `--lowerQuality` flag
- Adjust rotation for image orientation

## Credits

- Original Go library: [go-catprinter](https://git.boxo.cc/massivebox/go-catprinter)
- License: [MIT](LICENSE)
- Vue.js: [MIT](https://github.com/vuejs/core)
- TailwindCSS: [MIT](https://github.com/tailwindlabs/tailwindcss)

## License

This project is MIT licensed. See [LICENSE](LICENSE) for details.

---

<p align="center">
Made with ❤️ for CAT thermal printers
</p>