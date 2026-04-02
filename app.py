#!/usr/bin/env python3
"""
CAT Printer Web Interface
=====================
Enhanced Flask server for CAT thermal printer with:
- Keep-alive system (prevent auto shut-off)
- Auto-reconnect logic
- PDF printing support
- Password protection
- Docker support

Based on go-catprinter: https://git.boxo.cc/massivebox/go-catprinter
License: MIT
"""

import os
import json
import subprocess
import threading
import time
import traceback
import textwrap
import uuid
from functools import wraps
from datetime import datetime

from flask import Flask, render_template, request, jsonify, make_response
from PIL import Image, ImageDraw, ImageFont

# Try to import optional dependencies
try:
    from flask_httpauth import HTTPBasicAuth
    from werkzeug.security import generate_password_hash, check_password_hash
    FLASK_AUTH_AVAILABLE = True
except ImportError:
    FLASK_AUTH_AVAILABLE = False
    print("Warning: flask-httpauth not installed. Password protection disabled.")

try:
    import fitz  # PyMuPDF for PDF support
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("Warning: PyMuPDF not installed. PDF printing disabled.")

# Configuration
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Initialize auth if available
if FLASK_AUTH_AVAILABLE:
    auth = HTTPBasicAuth()
    users = {
        os.environ.get('ADMIN_USER', 'admin'): generate_password_hash(
            os.environ.get('ADMIN_PASSWORD', 'changeme')
        )
    }
    
    @auth.verify_password
    def verify_password(username, password):
        if username in users:
            return check_password_hash(users[username], password)
        return False
else:
    auth = None

# Environment configuration
WORKDIR = os.environ.get('PRINTER_WORKDIR', '/home/rgodim/catprinter-test/go-catprinter')
DATA_FILE = os.environ.get('DATA_FILE', os.path.join(WORKDIR, 'tareas.json'))
MAC_PRINTER = os.environ.get('CAT_PRINTER_MAC', 'A1:49:35:A0:C8:79')
FLASK_PORT = int(os.environ.get('FLASK_PORT', '5000'))
ENABLE_AUTH = os.environ.get('ENABLE_AUTH', 'false').lower() == 'true'
PING_INTERVAL = int(os.environ.get('PING_INTERVAL', '150'))  # 2.5 minutes default

# Ensure workdir exists
os.makedirs(WORKDIR, exist_ok=True)


# =============================================================================
# Authentication Decorator
# =============================================================================

def requires_auth(f):
    """Decorator to require authentication for routes."""
    if not ENABLE_AUTH or not FLASK_AUTH_AVAILABLE:
        return f
    
    @auth.login_required()
    @wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated


# =============================================================================
# Keep-Alive System
# =============================================================================

class KeepAliveSystem:
    """System to keep the printer awake by sending periodic pings."""
    
    def __init__(self, interval=PING_INTERVAL):
        self.interval = interval
        self.running = False
        self.last_ping = None
        self.last_status = None
        self.connection_error = None
        self.lock = threading.Lock()
    
    def start(self):
        """Start the keep-alive thread."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print(f"[KeepAlive] Started with {self.interval}s interval")
    
    def stop(self):
        """Stop the keep-alive thread."""
        self.running = False
    
    def _run(self):
        """Main keep-alive loop."""
        while self.running:
            try:
                self._ping()
            except Exception as e:
                with self.lock:
                    self.connection_error = str(e)
            time.sleep(self.interval)
    
    def _ping(self):
        """Send a dummy print command to keep printer awake."""
        dummy_img = os.path.join(WORKDIR, 'demo.jpg')
        
        if not os.path.exists(dummy_img):
            # Create a minimal dummy image if demo.jpg doesn't exist
            img = Image.new('RGB', (384, 100), color='white')
            img.save(dummy_img)
        
        # Use --dontPrint to avoid actually printing
        comando = f"sudo {WORKDIR}/catprinter --mac {MAC_PRINTER} --image {dummy_img} --dontPrint"
        
        result = subprocess.run(
            comando, 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            timeout=30
        )
        
        with self.lock:
            self.last_ping = datetime.now().isoformat()
            if result.returncode == 0:
                self.last_status = 'ok'
                self.connection_error = None
            else:
                self.last_status = 'error'
                self.connection_error = result.stderr.decode()
        
        print(f"[KeepAlive] Ping sent: {self.last_status}")
    
    def get_status(self):
        """Get current keep-alive status."""
        with self.lock:
            return {
                'running': self.running,
                'last_ping': self.last_ping,
                'last_status': self.last_status,
                'connection_error': self.connection_error,
                'interval': self.interval
            }


# Create global keep-alive instance
keep_alive = KeepAliveSystem(PING_INTERVAL)


# =============================================================================
# Auto-Reconnection System
# =============================================================================

class ConnectionManager:
    """Manager for printer connection with auto-reconnect."""
    
    def __init__(self, max_retries=3, retry_delay=2):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.connected = False
        self.last_error = None
        self.lock = threading.Lock()
    
    def reconnect(self):
        """Attempt to reconnect to the printer."""
        print(f"[ConnectionManager] Attempting to reconnect (max {self.max_retries} retries)...")
        
        for attempt in range(self.max_retries):
            try:
                # Test connection with a simple scan
                result = subprocess.run(
                    f"sudo {WORKDIR}/catprinter --mac {MAC_PRINTER} --scan",
                    shell=True,
                    capture_output=True,
                    timeout=15
                )
                
                if result.returncode == 0:
                    with self.lock:
                        self.connected = True
                        self.last_error = None
                    print(f"[ConnectionManager] Reconnected successfully on attempt {attempt + 1}")
                    return True
                    
            except Exception as e:
                with self.lock:
                    self.last_error = str(e)
                print(f"[ConnectionManager] Attempt {attempt + 1} failed: {e}")
            
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)
        
        with self.lock:
            self.connected = False
        print(f"[ConnectionManager] Failed to reconnect after {self.max_retries} attempts")
        return False
    
    def get_status(self):
        """Get connection status."""
        with self.lock:
            return {
                'connected': self.connected,
                'last_error': self.last_error,
                'max_retries': self.max_retries
            }


# Create global connection manager
conn_manager = ConnectionManager()


# =============================================================================
# Print Job System
# =============================================================================

class PrintJobSystem:
    """System for handling print jobs with retry logic."""
    
    def __init__(self):
        self.jobs = []
        self.lock = threading.Lock()
    
    def submit(self, job_id, img_path, comando_base, copias):
        """Submit a print job."""
        with self.lock:
            self.jobs.append({
                'id': job_id,
                'img_path': img_path,
                'copias': copias,
                'status': 'pending',
                'created': datetime.now().isoformat()
            })
        
        # Run job in background thread
        thread = threading.Thread(
            target=self._execute_job,
            args=(job_id, comando_base, copias),
            daemon=True
        )
        thread.start()
        
        return job_id
    
    def _execute_job(self, job_id, comando_base, copias):
        """Execute a print job with retry logic."""
        comando_reintento = f"for i in 1 2 3; do {comando_base} && break; sleep 1; done"
        
        with self.lock:
            job = next((j for j in self.jobs if j['id'] == job_id), None)
        
        if not job:
            return
        
        print(f"[*] Starting job {job_id}: {copias} copy(ies)")
        
        for c in range(copias):
            print(f"[->] Printing copy {c+1}/{copias}")
            
            try:
                result = subprocess.run(
                    comando_reintento,
                    shell=True,
                    capture_output=True,
                    timeout=60
                )
                
                if result.returncode != 0:
                    # Try to reconnect
                    conn_manager.reconnect()
                    
            except Exception as e:
                print(f"[-] Print error: {e}")
                conn_manager.reconnect()
            
            if c < copias - 1:
                time.sleep(2)  # Pause between copies to protect battery
        
        with self.lock:
            for j in self.jobs:
                if j['id'] == job_id:
                    j['status'] = 'completed'
                    j['completed'] = datetime.now().isoformat()
        
        # Cleanup image file
        img_path = job.get('img_path')
        if img_path and os.path.exists(img_path):
            try:
                os.remove(img_path)
                print(f"[+] Job {job_id} file cleaned: {img_path}")
            except Exception as e:
                print(f"[-] Cleanup error: {e}")
    
    def get_jobs(self):
        """Get all jobs."""
        with self.lock:
            return list(self.jobs)
    
    def get_job(self, job_id):
        """Get a specific job."""
        with self.lock:
            return next((j for j in self.jobs if j['id'] == job_id), None)


# Create global print job system
print_jobs = PrintJobSystem()


# =============================================================================
# Utility Functions
# =============================================================================

def obtener_fuentes():
    """Load fonts for image rendering."""
    font_paths = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf',
    ]
    
    try:
        bold = ImageFont.truetype(font_paths[0], 26)
        normal = ImageFont.truetype(font_paths[1], 22)
        small = ImageFont.truetype(font_paths[2], 16)
        return bold, normal, small
    except:
        f = ImageFont.load_default()
        return f, f, f


def crear_imagen_tareas(titulo_lista, tareas):
    """Create a task list image."""
    font_bold, font_normal, font_small = obtener_fuentes()
    
    alto_header = 80
    alto_por_tarea = 60
    alto_total = alto_header + (len(tareas) * alto_por_tarea) + 5
    
    img = Image.new('RGB', (384, alto_total), color='white')
    d = ImageDraw.Draw(img)
    
    # Title
    d.text((20, 20), f"=== {titulo_lista} ===", fill='black', font=font_bold)
    d.line([(20, 60), (364, 60)], fill='black', width=3)
    
    # Tasks
    y = alto_header
    for t in tareas:
        d.text((20, y), f"[ ] {t['nombre']}", fill='black', font=font_normal)
        if t.get('fecha'):
            d.text((200, y + 28), f"Límite: {t['fecha']}", fill='black', font=font_small)
        d.line([(20, y + 50), (364, y + 50)], fill='gray', width=1)
        y += alto_por_tarea
    
    return img


def crear_imagen_texto(texto):
    """Create a text image."""
    _, font_normal, _ = obtener_fuentes()
    
    lineas = textwrap.wrap(texto, width=28)
    alto_total = 40 + (len(lineas) * 30) + 10
    
    img = Image.new('RGB', (384, alto_total), color='white')
    d = ImageDraw.Draw(img)
    
    y = 20
    for linea in lineas:
        d.text((20, y), linea, fill='black', font=font_normal)
        y += 30
    
    return img


def convertir_pdf_a_imagenes(file_bytes, output_dir):
    """Convert PDF to images using PyMuPDF."""
    if not PDF_SUPPORT:
        raise Exception("PDF support not installed. Install PyMuPDF: pip install pymupdf")
    
    # Save PDF to temp file
    pdf_path = os.path.join(output_dir, f'temp_{uuid.uuid4()}.pdf')
    with open(pdf_path, 'wb') as f:
        f.write(file_bytes)
    
    image_paths = []
    
    try:
        doc = fitz.open(pdf_path)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x scale for better quality
            
            img_path = os.path.join(output_dir, f'pdf_page_{page_num}.png')
            pix.save(img_path)
            image_paths.append(img_path)
        
        doc.close()
    
    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
    
    return image_paths


# =============================================================================
# Flask Routes
# =============================================================================

@app.route('/')
@requires_auth
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/api/health')
def api_health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'keep_alive': keep_alive.get_status(),
        'connection': conn_manager.get_status(),
        'pdf_support': PDF_SUPPORT,
        'auth_enabled': ENABLE_AUTH
    })


@app.route('/api/status')
@requires_auth
def api_status():
    """Get printer status."""
    return jsonify({
        'keep_alive': keep_alive.get_status(),
        'connection': conn_manager.get_status(),
        'jobs': print_jobs.get_jobs(),
        'mac': MAC_PRINTER,
        'running': keep_alive.running
    })


@app.route('/api/tareas', methods=['GET', 'POST'])
@requires_auth
def api_tareas():
    """Get or save task list."""
    try:
        if request.method == 'POST':
            with open(DATA_FILE, 'w') as f:
                json.dump(request.json, f)
            return jsonify({"status": "ok"})
        
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return jsonify(json.load(f))
        return jsonify([])
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/imprimir/tareas', methods=['POST'])
@requires_auth
def api_imprimir_tareas():
    """Print task list."""
    try:
        datos = request.json
        titulo_lista = datos.get('titulo', 'LISTA DE TAREAS')
        tareas = datos.get('tareas', [])
        copias = max(1, min(10, int(datos.get('copias', 1))))
        
        img = crear_imagen_tareas(titulo_lista, tareas)
        
        timestamp = int(time.time())
        job_id = f"tareas_{timestamp}"
        img_path = os.path.join(WORKDIR, f"print_job_{timestamp}.png")
        img.save(img_path)
        
        comando_base = f"sudo {WORKDIR}/catprinter --mac {MAC_PRINTER} --image {img_path} --lowerQuality"
        
        job_id = print_jobs.submit(job_id, img_path, comando_base, copias)
        
        return jsonify({"status": "ok", "job_id": job_id})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/imprimir/texto', methods=['POST'])
@requires_auth
def api_imprimir_texto():
    """Print free text."""
    try:
        datos = request.json
        texto = datos.get('texto', '')
        copias = max(1, min(10, int(datos.get('copias', 1))))
        
        img = crear_imagen_texto(texto)
        
        timestamp = int(time.time())
        job_id = f"texto_{timestamp}"
        img_path = os.path.join(WORKDIR, f"print_text_{timestamp}.png")
        img.save(img_path)
        
        comando_base = f"sudo {WORKDIR}/catprinter --mac {MAC_PRINTER} --image {img_path} --lowerQuality"
        
        job_id = print_jobs.submit(job_id, img_path, comando_base, copias)
        
        return jsonify({"status": "ok", "job_id": job_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/imprimir/imagen', methods=['POST'])
@requires_auth
def api_imprimir_imagen():
    """Print an image."""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        copias = max(1, min(10, int(request.form.get('copies', 1))))
        rotacion = int(request.form.get('rotation', 0))
        
        # Process image with Pillow
        img = Image.open(file.stream).convert("RGB")
        if rotacion != 0:
            img = img.rotate(-rotacion, expand=True)
        
        timestamp = int(time.time())
        job_id = f"photo_{timestamp}"
        img_path = os.path.join(WORKDIR, f"print_photo_{timestamp}.png")
        img.save(img_path)
        
        # Photos use higher quality (dithering)
        comando_base = f"sudo {WORKDIR}/catprinter --mac {MAC_PRINTER} --image {img_path}"
        
        job_id = print_jobs.submit(job_id, img_path, comando_base, copias)
        
        return jsonify({"status": "ok", "job_id": job_id})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/imprimir/pdf', methods=['POST'])
@requires_auth
def api_imprimir_pdf():
    """Print a PDF."""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        if not PDF_SUPPORT:
            return jsonify({"error": "PDF support not installed"}), 400
        
        file = request.files['file']
        copias = max(1, min(10, int(request.form.get('copies', 1))))
        
        # Read PDF and convert to images
        image_paths = convertir_pdf_a_imagenes(file.read(), WORKDIR)
        
        job_ids = []
        for i, img_path in enumerate(image_paths):
            job_id = f"pdf_{int(time.time())}_{i}"
            comando_base = f"sudo {WORKDIR}/catprinter --mac {MAC_PRINTER} --image {img_path}"
            
            job_id = print_jobs.submit(job_id, img_path, comando_base, copias)
            job_ids.append(job_id)
        
        return jsonify({"status": "ok", "jobs": job_ids})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/keepalive/start', methods=['POST'])
@requires_auth
def api_keepalive_start():
    """Start keep-alive system."""
    keep_alive.start()
    return jsonify({"status": "ok", "running": True})


@app.route('/api/keepalive/stop', methods=['POST'])
@requires_auth
def api_keepalive_stop():
    """Stop keep-alive system."""
    keep_alive.stop()
    return jsonify({"status": "ok", "running": False})


@app.route('/api/reconnect', methods=['POST'])
@requires_auth
def api_reconnect():
    """Force reconnection."""
    success = conn_manager.reconnect()
    return jsonify({"status": "ok", "connected": success})


# =============================================================================
# Error Handlers
# =============================================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Server error"}), 500


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    # Start keep-alive system automatically
    keep_alive.start()
    
    print(f"\n{'='*50}")
    print("CAT Printer Web Interface")
    print(f"{'='*50}")
    print(f"MAC Address: {MAC_PRINTER}")
    print(f"Workdir: {WORKDIR}")
    print(f"Auth: {'Enabled' if ENABLE_AUTH else 'Disabled'}")
    print(f"Ping Interval: {PING_INTERVAL}s")
    print(f"PDF Support: {'Yes' if PDF_SUPPORT else 'No'}")
    print(f"{'='*50}\n")
    
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)