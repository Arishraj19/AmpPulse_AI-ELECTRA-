#!/usr/bin/env python3
"""
AmpPulse AI - Windows-friendly one-shot ESP32 + laptop setup script.

Windows workflow:

    python setup_esp32.py

Or:

    python setup_esp32.py --ssid MyWifi --password hunter2

The script:

  1. Creates backend\\.venv if needed.
  2. Installs backend Python dependencies if missing.
  3. Generates backend secrets when required.
  4. Starts FastAPI/Uvicorn on 0.0.0.0:8000.
  5. Writes Wi-Fi credentials into the ESP32 sketch.
  6. Detects Windows COM ports.
  7. Uploads using arduino-cli if available.
  8. Starts frontend using:
         python -m http.server 5500
  9. Opens the browser.
 10. Can verify ESP32 /data directly over Wi-Fi.

Examples:

    python setup_esp32.py

    python setup_esp32.py --gui

    python setup_esp32.py --status

    python setup_esp32.py --stop

    python setup_esp32.py --ssid MyWifi --password hunter2

    python setup_esp32.py --ssid MyWifi --password hunter2 --install-cli

    python setup_esp32.py --esp32-ip 192.168.1.7 --skip-upload

Notes:

    Backend:
        backend\\.venv\\Scripts\\python.exe -m uvicorn app.main:app
        --host 0.0.0.0 --port 8000

    Frontend:
        python -m http.server 5500 --bind 0.0.0.0
"""

import argparse
import glob
import json
import os
import platform
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


# ================================================================
# Paths
# ================================================================

ROOT = Path(__file__).resolve().parent

BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

ENV_FILE = BACKEND_DIR / ".env"

SKETCH_FILE = (
    ROOT
    / "arduino"
    / "amppulse_esp32"
    / "amppulse_esp32.ino"
)

BACKEND_LOG = BACKEND_DIR / "uvicorn.log"
FRONTEND_LOG = FRONTEND_DIR / "server.log"

BACKEND_PID_FILE = BACKEND_DIR / "uvicorn.pid"
FRONTEND_PID_FILE = FRONTEND_DIR / "server.pid"


SKETCH_PLACEHOLDERS = {
    "WIFI_SSID": (
        "ELECTRA",
        "YOUR_WIFI_SSID",
        "",
    ),
    "WIFI_PASSWORD": (
        "Home@4127",
        "YOUR_WIFI_PASSWORD",
        "",
    ),
}


SKETCH_DEFINES = {
    "WIFI_SSID":
        r'const char\* WIFI_SSID\s*=\s*"((?:[^"\\]|\\.)*)"',
    "WIFI_PASSWORD":
        r'const char\* WIFI_PASSWORD\s*=\s*"((?:[^"\\]|\\.)*)"',
}


# ================================================================
# Logging
# ================================================================

def log(msg: str) -> None:
    print(f"\n== {msg}")


# ================================================================
# C string helpers
# ================================================================

def unescape_c(value: str) -> str:
    return re.sub(r'\\(["\\])', r'\1', value)


def c_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


# ================================================================
# Environment helpers
# ================================================================

def read_env() -> dict:
    env = {}

    if not ENV_FILE.exists():
        return env

    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)

        env[key.strip()] = value.strip()

    return env


def write_env(env: dict) -> None:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)

    lines = []

    for key in sorted(env.keys()):

        value = env[key]
        comment = ""

        if key == "HOST":
            comment = (
                " --- Server ---\n"
                "# Host the backend on all interfaces.\n"
            )

        elif key == "DATABASE_URL":
            comment = (
                " --- Database ---\n"
                "# SQLite for MVP.\n"
            )

        elif key == "JWT_SECRET":
            comment = (
                " --- Security ---\n"
                "# Secret used to sign JWT tokens.\n"
            )

        elif key == "DEVICE_PROVISION_KEY":
            comment = (
                "# Backend device provisioning key.\n"
            )

        elif key == "CORS_ORIGINS":
            comment = (
                " --- CORS ---\n"
                "# Frontend origins allowed to call the API.\n"
            )

        elif key == "SEED_USER_EMAIL":
            comment = (
                " --- Seed user ---\n"
            )

        lines.append(f"{comment}{key}={value}\n")

    ENV_FILE.write_text(
        "".join(lines),
        encoding="utf-8",
    )

    print(
        f"[env] Wrote {ENV_FILE.name} "
        f"({len(env)} keys)"
    )


# ================================================================
# HTTP helpers
# ================================================================

def http_json(
    method: str,
    url: str,
    data=None,
    headers: dict | None = None,
    timeout: int = 5,
):
    body = (
        json.dumps(data).encode("utf-8")
        if data is not None
        else None
    )

    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Content-Type": "application/json",
            **(headers or {}),
        },
    )

    with urllib.request.urlopen(
        req,
        timeout=timeout,
    ) as response:

        raw = response.read().decode("utf-8")

        return (
            response.status,
            json.loads(raw) if raw else {},
        )


def api_is_up(port: int) -> bool:
    try:
        http_json(
            "GET",
            f"http://127.0.0.1:{port}/api/v1/health",
        )
        return True

    except Exception:
        return False


# ================================================================
# Python / virtualenv
# ================================================================

def venv_python() -> Path:
    """
    Return the correct Python executable for the OS.
    """

    venv = BACKEND_DIR / ".venv"

    if platform.system() == "Windows":
        return venv / "Scripts" / "python.exe"

    return venv / "bin" / "python"


def backend_python() -> str:
    """
    Create backend virtualenv and install dependencies.
    """

    venv = BACKEND_DIR / ".venv"
    py = venv_python()

    if not py.exists():

        log("Creating backend virtualenv (.venv)")

        subprocess.run(
            [
                sys.executable,
                "-m",
                "venv",
                str(venv),
            ],
            check=True,
        )

    try:

        subprocess.run(
            [
                str(py),
                "-c",
                "import fastapi, uvicorn",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    except subprocess.CalledProcessError:

        log(
            "Installing backend dependencies "
            "into .venv"
        )

        subprocess.run(
            [
                str(py),
                "-m",
                "pip",
                "install",
                "--upgrade",
                "pip",
            ],
            check=True,
        )

        requirements = (
            BACKEND_DIR / "requirements.txt"
        )

        subprocess.run(
            [
                str(py),
                "-m",
                "pip",
                "install",
                "-r",
                str(requirements),
            ],
            check=True,
        )

    return str(py)


# ================================================================
# Environment secrets
# ================================================================

def ensure_env_secrets(env: dict) -> bool:

    changed = False

    if env.get("JWT_SECRET", "").startswith("change_"):

        env["JWT_SECRET"] = secrets.token_hex(32)

        print("[env] Generated new JWT_SECRET")

        changed = True

    if env.get(
        "DEVICE_PROVISION_KEY",
        "",
    ).startswith("change_"):

        env["DEVICE_PROVISION_KEY"] = (
            "provision_"
            + secrets.token_urlsafe(24)
        )

        print(
            "[env] Generated DEVICE_PROVISION_KEY"
        )

        changed = True

    if changed:
        write_env(env)

    return changed


# ================================================================
# Backend
# ================================================================

def start_backend(port: int) -> None:

    if api_is_up(port):

        print(
            f"[backend] Already running at "
            f"127.0.0.1:{port}"
        )

        return

    log(
        f"Starting backend on "
        f"0.0.0.0:{port}"
    )

    py = backend_python()

    BACKEND_LOG.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_file = BACKEND_LOG.open(
        "w",
        encoding="utf-8",
    )

    command = [
        py,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
    ]

    # Add --reload only when explicitly requested.
    # Production-like startup is more reliable for setup.
    #
    # command.append("--reload")

    creationflags = 0

    if platform.system() == "Windows":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
        )

    proc = subprocess.Popen(
        command,
        cwd=str(BACKEND_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )

    BACKEND_PID_FILE.write_text(
        str(proc.pid),
        encoding="utf-8",
    )

    deadline = time.time() + 60

    while time.time() < deadline:

        if api_is_up(port):

            print(
                "[backend] Backend is up."
            )

            return

        if proc.poll() is not None:

            print(
                BACKEND_LOG.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )[-5000:]
                if BACKEND_LOG.exists()
                else ""
            )

            sys.exit(
                "Backend process exited early."
            )

        time.sleep(1)

    sys.exit(
        "Backend did not become healthy "
        "within 60 seconds. "
        f"See {BACKEND_LOG}"
    )


# ================================================================
# Sketch helpers
# ================================================================

def read_sketch_defines() -> dict:

    values = {}

    if not SKETCH_FILE.exists():
        return values

    text = SKETCH_FILE.read_text(
        encoding="utf-8"
    )

    for name, pattern in SKETCH_DEFINES.items():

        match = re.search(
            pattern,
            text,
        )

        if match:
            values[name] = unescape_c(
                match.group(1)
            )

    return values


def patch_sketch(values: dict) -> None:

    text = SKETCH_FILE.read_text(
        encoding="utf-8"
    )

    for name, new_value in values.items():

        pattern = SKETCH_DEFINES[name]

        replacement = (
            f'const char* {name} = '
            f'"{c_escape(new_value)}";'
        )

        text, count = re.subn(
            pattern,
            lambda _match: replacement,
            text,
            count=1,
        )

        if count != 1:

            sys.exit(
                f"Could not find {name} "
                f"in {SKETCH_FILE}"
            )

    SKETCH_FILE.write_text(
        text,
        encoding="utf-8",
    )

    print(
        f"[sketch] Configured "
        f"{len(values)} values"
    )


# ================================================================
# Networking
# ================================================================

def detect_lan_ip() -> str:

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    try:

        sock.connect(
            ("8.8.8.8", 80)
        )

        return sock.getsockname()[0]

    except OSError:

        return ""

    finally:

        sock.close()


# ================================================================
# Windows COM port detection
# ================================================================

def find_serial_port() -> str:
    """
    Detect ESP32 COM port on Windows.

    Examples:
        COM3
        COM4
        COM10
    """

    if platform.system() != "Windows":

        for pattern in (
            "/dev/ttyUSB*",
            "/dev/ttyACM*",
        ):

            hits = sorted(
                glob.glob(pattern)
            )

            if hits:
                return hits[0]

        return ""

    try:

        import serial.tools.list_ports

        ports = list(
            serial.tools.list_ports.comports()
        )

        if not ports:
            return ""

        # Prefer common ESP32 USB chips.
        preferred = (
            "CP210",
            "CH340",
            "CH910",
            "USB-SERIAL",
            "FTDI",
            "ESP32",
        )

        for port in ports:

            description = (
                port.description or ""
            ).upper()

            manufacturer = (
                port.manufacturer or ""
            ).upper()

            text = (
                description
                + " "
                + manufacturer
            )

            if any(
                item in text
                for item in preferred
            ):

                return port.device

        # Otherwise use the first COM port.
        return ports[0].device

    except ImportError:

        # Fallback without pyserial.
        try:

            output = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "[System.IO.Ports.SerialPort]::GetPortNames()",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            )

            ports = [
                x.strip()
                for x in output.splitlines()
                if x.strip()
            ]

            return ports[0] if ports else ""

        except Exception:

            return ""


# ================================================================
# Process helpers
# ================================================================

def _read_pidfile(path: Path) -> tuple[int, str]:

    if not path.exists():
        return 0, ""

    try:

        parts = path.read_text(
            encoding="utf-8"
        ).split()

        return (
            int(parts[0]),
            parts[1] if len(parts) > 1 else "",
        )

    except (
        ValueError,
        OSError,
    ):

        return 0, ""


def _alive(pid: int) -> bool:

    if not pid:
        return False

    try:

        os.kill(pid, 0)

        return True

    except (
        ProcessLookupError,
        PermissionError,
    ):

        return False

    except OSError:

        return False


def _cmdline(pid: int) -> str:

    try:

        if platform.system() == "Windows":

            output = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        f"(Get-CimInstance "
                        f"Win32_Process -Filter "
                        f"'ProcessId={pid}').CommandLine"
                    ),
                ],
                capture_output=True,
                text=True,
            )

            return output.stdout.strip()

        output = subprocess.run(
            [
                "ps",
                "-p",
                str(pid),
                "-o",
                "command=",
            ],
            capture_output=True,
            text=True,
        )

        return output.stdout.strip()

    except Exception:

        return ""


def _terminate(
    pid: int,
    label: str,
    wait_s: int = 8,
) -> None:

    if not pid:
        return

    print(
        f"  Stopping {label} "
        f"(pid {pid})"
    )

    try:

        if platform.system() == "Windows":

            subprocess.run(
                [
                    "taskkill",
                    "/PID",
                    str(pid),
                    "/T",
                    "/F",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            print(
                f"  {label} stopped."
            )

            return

        os.kill(
            pid,
            signal.SIGTERM,
        )

    except Exception:
        pass

    deadline = time.time() + wait_s

    while time.time() < deadline:

        if not _alive(pid):

            print(
                f"  {label} stopped."
            )

            return

        time.sleep(0.3)

    try:

        os.kill(
            pid,
            signal.SIGKILL,
        )

    except Exception:
        pass

    print(
        f"  {label} force-killed."
    )


# ================================================================
# Stop servers
# ================================================================

def stop_servers() -> None:

    print(
        "\n== Stopping AmpPulse servers"
    )

    # ------------------------------------------------------------
    # Backend
    # ------------------------------------------------------------

    pid, _ = _read_pidfile(
        BACKEND_PID_FILE
    )

    if pid and _alive(pid):

        command = _cmdline(pid).lower()

        if (
            "uvicorn" in command
            or "app.main:app" in command
        ):

            _terminate(
                pid,
                "backend",
            )

        else:

            print(
                "  Recorded backend PID "
                "does not look like AmpPulse. "
                "Leaving it alone."
            )

    else:

        print(
            "  No AmpPulse backend detected."
        )

    BACKEND_PID_FILE.unlink(
        missing_ok=True
    )

    # ------------------------------------------------------------
    # Frontend
    # ------------------------------------------------------------

    fpid, fport = _read_pidfile(
        FRONTEND_PID_FILE
    )

    if fpid and _alive(fpid):

        command = _cmdline(fpid).lower()

        if (
            "http.server" in command
            or "python" in command
        ):

            _terminate(
                fpid,
                f"frontend "
                f"(port {fport or '?'})",
            )

    else:

        print(
            "  No AmpPulse frontend detected."
        )

    FRONTEND_PID_FILE.unlink(
        missing_ok=True
    )

    print(
        "\n  Done."
    )


# ================================================================
# Arduino CLI
# ================================================================

def have_arduino_cli() -> bool:

    return (
        shutil.which("arduino-cli")
        is not None
    )


def find_arduino_cli() -> str:

    cli = shutil.which(
        "arduino-cli"
    )

    if cli:
        return cli

    candidates = [
        Path.home()
        / "AppData"
        / "Local"
        / "Arduino15"
        / "arduino-cli.exe",

        Path.home()
        / ".local"
        / "bin"
        / "arduino-cli.exe",

        Path(
            "C:/Program Files/Arduino CLI/arduino-cli.exe"
        ),
    ]

    for candidate in candidates:

        if candidate.exists():
            return str(candidate)

    return ""


def install_arduino_cli() -> str:

    existing = find_arduino_cli()

    if existing:
        return existing

    if platform.system() != "Windows":

        sys.exit(
            "Automatic arduino-cli installation "
            "in this version is intended for Windows."
        )

    install_dir = (
        Path.home()
        / "AppData"
        / "Local"
        / "Programs"
        / "arduino-cli"
    )

    install_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    exe = (
        install_dir
        / "arduino-cli.exe"
    )

    version = "1.1.1"

    url = (
        "https://github.com/arduino/arduino-cli/"
        f"releases/download/v{version}/"
        f"arduino-cli_{version}_Windows_64bit.zip"
    )

    zip_file = (
        install_dir
        / "arduino-cli.zip"
    )

    log(
        f"Downloading arduino-cli "
        f"v{version}"
    )

    try:

        with urllib.request.urlopen(
            url,
            timeout=180,
        ) as response, zip_file.open(
            "wb"
        ) as file:

            file.write(
                response.read()
            )

    except Exception as exc:

        sys.exit(
            "Could not download arduino-cli: "
            f"{exc}"
        )

    import zipfile

    try:

        with zipfile.ZipFile(
            zip_file,
            "r",
        ) as archive:

            for member in archive.namelist():

                if member.lower().endswith(
                    "arduino-cli.exe"
                ):

                    with archive.open(
                        member
                    ) as source, exe.open(
                        "wb"
                    ) as target:

                        shutil.copyfileobj(
                            source,
                            target,
                        )

                    break

    finally:

        zip_file.unlink(
            missing_ok=True
        )

    if not exe.exists():

        sys.exit(
            "arduino-cli.exe was not found "
            "inside downloaded archive."
        )

    print(
        f"[cli] Installed at {exe}"
    )

    return str(exe)


# ================================================================
# Upload
# ================================================================

def upload_sketch(
    cli: str,
    port: str,
) -> bool:

    fqbn = "esp32:esp32:esp32"

    sketch_dir = SKETCH_FILE.parent

    espressif_index = (
        "https://espressif.github.io/"
        "arduino-esp32/package_esp32_index.json"
    )

    subprocess.run(
        [
            cli,
            "config",
            "init",
        ],
        capture_output=True,
        text=True,
    )

    subprocess.run(
        [
            cli,
            "config",
            "add",
            "board_manager.additional_urls",
            espressif_index,
        ],
        check=True,
    )

    print(
        "[cli] Installing Arduino libraries..."
    )

    subprocess.run(
        [
            cli,
            "lib",
            "install",
            "ArduinoJson",
        ],
        capture_output=True,
        text=True,
    )

    subprocess.run(
        [
            cli,
            "lib",
            "install",
            "DHT sensor library",
        ],
        capture_output=True,
        text=True,
    )

    subprocess.run(
        [
            cli,
            "lib",
            "install",
            "Adafruit Unified Sensor",
        ],
        capture_output=True,
        text=True,
    )

    print(
        "[cli] Installing ESP32 core..."
    )

    subprocess.run(
        [
            cli,
            "core",
            "update-index",
        ],
        check=True,
    )

    subprocess.run(
        [
            cli,
            "core",
            "install",
            fqbn,
        ],
        check=False,
    )

    listed = subprocess.run(
        [
            cli,
            "core",
            "list",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    if "esp32:esp32" not in listed:

        print(listed)

        sys.exit(
            "FATAL: esp32:esp32 core "
            "was not installed."
        )

    print(
        "[cli] ESP32 core ready."
    )

    log(
        "Compiling ESP32 sketch"
    )

    subprocess.run(
        [
            cli,
            "compile",
            "--fqbn",
            fqbn,
            str(sketch_dir),
        ],
        check=True,
    )

    log(
        f"Uploading ESP32 to {port}"
    )

    subprocess.run(
        [
            cli,
            "upload",
            "-p",
            port,
            "--fqbn",
            fqbn,
            str(sketch_dir),
        ],
        check=True,
    )

    print(
        "\n[upload] SUCCESS"
    )

    return True


def do_upload(
    port_arg=None,
    install_arg=False,
) -> bool:

    port = (
        port_arg
        or find_serial_port()
    )

    if not port:

        print(
            "\nNo ESP32 serial port detected."
        )

        if platform.system() == "Windows":

            print(
                "Check Windows Device Manager "
                "→ Ports (COM & LPT)."
            )

            print(
                "Typical ESP32 ports: COM3, COM4, "
                "COM5, etc."
            )

        return False

    print(
        f"[serial] ESP32 port: {port}"
    )

    cli = find_arduino_cli()

    if cli:

        return upload_sketch(
            cli,
            port,
        )

    if install_arg:

        cli = install_arduino_cli()

        return upload_sketch(
            cli,
            port,
        )

    print(
        "\narduino-cli was not found."
    )

    choice = input(
        "Auto-install arduino-cli and "
        "upload now? (y/N): "
    ).strip().lower()

    if choice in (
        "y",
        "yes",
    ):

        cli = install_arduino_cli()

        return upload_sketch(
            cli,
            port,
        )

    print(
        "\nManual upload:"
    )

    print(
        "Open the sketch in Arduino IDE."
    )

    print(
        "Board: ESP32 Dev Module"
    )

    print(
        f"Port: {port}"
    )

    print(
        "Press Upload."
    )

    return False


# ================================================================
# ESP32 verification
# ================================================================

def probe_esp32(
    ip: str,
    port: int = 80,
    timeout: int = 4,
) -> dict:

    url = (
        f"http://{ip}:{port}/data"
    )

    with urllib.request.urlopen(
        url,
        timeout=timeout,
    ) as response:

        body = (
            response
            .read()
            .decode()
            .strip()
        )

    return (
        json.loads(body)
        if body
        else {}
    )


def verify_esp32(
    ip: str,
    wait_s: int = 30,
) -> None:

    print(
        f"[verify] Probing "
        f"http://{ip}:80/data"
    )

    deadline = (
        time.time()
        + wait_s
    )

    while time.time() < deadline:

        try:

            data = probe_esp32(ip)

            if "voltage" in data:

                print(
                    "\n  [verify] Live reading:"
                )

                print(
                    f"    Voltage     : "
                    f"{data.get('voltage')} V"
                )

                print(
                    f"    Current     : "
                    f"{data.get('current')} A"
                )

                print(
                    f"    Power       : "
                    f"{data.get('power')} W"
                )

                print(
                    f"    Temperature : "
                    f"{data.get('temperature')} C"
                )

                print(
                    f"    Relay 1     : "
                    f"{data.get('relay1')}"
                )

                print(
                    f"    Relay 2     : "
                    f"{data.get('relay2')}"
                )

                print(
                    "\n[verify] SUCCESS - "
                    "ESP32 web server is reachable."
                )

                return

        except Exception:
            pass

        time.sleep(2)

    print(
        f"\n[verify] No response from "
        f"{ip} within {wait_s}s."
    )

    print(
        "\nCheck:"
    )

    print(
        "  - ESP32 is powered"
    )

    print(
        "  - ESP32 and laptop are on "
        "the same Wi-Fi"
    )

    print(
        "  - Windows Firewall allows "
        "local network traffic"
    )

    print(
        "  - ESP32 IP shown in Serial Monitor"
    )

    print(
        "  - Serial Monitor baud rate = 115200"
    )


def prompt_esp32_ip(
    existing: dict,
    arg=None,
) -> str:

    ip = arg or ""

    if not ip:

        ip = input(
            "ESP32 IP address: "
        ).strip()

    if not ip:

        sys.exit(
            "An ESP32 IP address is required."
        )

    return ip


# ================================================================
# Frontend
# ================================================================

def _page_ok(
    base: str,
    path: str,
) -> bool:

    try:

        with urllib.request.urlopen(
            base + path,
            timeout=2,
        ) as response:

            return (
                b"AmpPulse AI"
                in response.read(4096)
            )

    except Exception:

        return False


def start_frontend_server() -> str:

    # Check existing server first.
    for path in (
        "/",
        "/index.html",
    ):

        if _page_ok(
            "http://127.0.0.1:5500",
            path,
        ):

            print(
                "[frontend] Already serving "
                "on port 5500."
            )

            return (
                "http://localhost:5500"
            )

    log(
        "Starting frontend server "
        "on port 5500"
    )

    FRONTEND_LOG.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_file = FRONTEND_LOG.open(
        "w",
        encoding="utf-8",
    )

    command = [
        sys.executable,
        "-m",
        "http.server",
        "5500",
        "--bind",
        "0.0.0.0",
    ]

    creationflags = 0

    if platform.system() == "Windows":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
        )

    proc = subprocess.Popen(
        command,
        cwd=str(FRONTEND_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )

    FRONTEND_PID_FILE.write_text(
        f"{proc.pid} 5500",
        encoding="utf-8",
    )

    deadline = time.time() + 10

    while time.time() < deadline:

        if _page_ok(
            "http://127.0.0.1:5500",
            "/",
        ):

            print(
                "[frontend] Frontend is up:"
                " http://localhost:5500"
            )

            return (
                "http://localhost:5500"
            )

        if proc.poll() is not None:
            break

        time.sleep(0.5)

    print(
        "[frontend] Could not start "
        "frontend server."
    )

    print(
        "Run manually:"
    )

    print(
        "  cd frontend"
    )

    print(
        "  python -m http.server 5500"
    )

    return (
        "http://localhost:5500"
    )


# ================================================================
# Browser
# ================================================================

def open_browser(url: str) -> None:

    try:

        if platform.system() == "Windows":

            os.startfile(url)

            return

    except Exception:
        pass

    try:

        if platform.system() == "Darwin":

            subprocess.Popen(
                ["open", url]
            )

            return

        subprocess.Popen(
            ["xdg-open", url]
        )

        return

    except Exception:
        pass

    print(
        f"Open this URL manually: {url}"
    )


# ================================================================
# Backend port
# ================================================================

def backend_port() -> int:

    try:

        return int(
            read_env().get(
                "PORT",
                "8000",
            )
        )

    except ValueError:

        return 8000


# ================================================================
# GUI
# ================================================================

def run_gui(
    open_win: bool = True,
) -> None:

    port = backend_port()

    start_backend(port)

    url = start_frontend_server()

    if open_win:
        open_browser(url)

    print(
        "\n================================================"
    )

    print(
        f"Frontend : {url}"
    )

    print(
        f"API      : http://localhost:{port}"
    )

    print(
        f"API docs : http://localhost:{port}/docs"
    )

    print(
        "\nLogin:"
    )

    print(
        "  Email    : demo@amppulse.ai"
    )

    print(
        "  Password : Demo@12345"
    )

    print(
        "\nThen enter the ESP32 IP in "
        "the dashboard's ESP32 Connect bar."
    )

    print(
        "================================================"
    )


# ================================================================
# Wi-Fi configuration
# ================================================================

def prompt_wifi(
    existing: dict,
    ssid_arg=None,
    password_arg=None,
) -> tuple[str, str]:

    ssid = (
        ssid_arg
        or existing.get(
            "WIFI_SSID",
            "",
        )
    )

    if (
        not ssid
        or ssid
        in SKETCH_PLACEHOLDERS[
            "WIFI_SSID"
        ]
    ):

        ssid = input(
            "Wi-Fi SSID: "
        ).strip()

    password = (
        password_arg
        or existing.get(
            "WIFI_PASSWORD",
            "",
        )
    )

    if (
        not password
        or password
        in SKETCH_PLACEHOLDERS[
            "WIFI_PASSWORD"
        ]
    ):

        password = input(
            "Wi-Fi password: "
        ).strip()

    if not ssid or not password:

        sys.exit(
            "Wi-Fi SSID and password "
            "are required."
        )

    return ssid, password


def configure_sketch(
    ssid_arg=None,
    password_arg=None,
) -> dict:

    if not SKETCH_FILE.exists():

        sys.exit(
            f"Sketch not found: "
            f"{SKETCH_FILE}"
        )

    existing = read_sketch_defines()

    ssid, password = prompt_wifi(
        existing,
        ssid_arg,
        password_arg,
    )

    values = {
        "WIFI_SSID": ssid,
        "WIFI_PASSWORD": password,
    }

    log(
        "Writing Wi-Fi configuration "
        "into ESP32 sketch"
    )

    patch_sketch(values)

    print(
        "\n== ESP32 Configuration"
    )

    print(
        f"  Wi-Fi       : {ssid}"
    )

    print(
        f"  Sketch      : {SKETCH_FILE}"
    )

    print(
        "  Relay CH1   : GPIO 25 "
        "(active LOW)"
    )

    print(
        "  Relay CH2   : GPIO 26 "
        "(active LOW)"
    )

    print(
        "  ZMPT101B    : GPIO 34"
    )

    print(
        "  DHT22       : GPIO 4"
    )

    print(
        "  Serial      : 115200 baud"
    )

    return values


# ================================================================
# Status
# ================================================================

def show_status() -> None:

    port = backend_port()

    sketch = (
        read_sketch_defines()
        or {}
    )

    backend_up = api_is_up(port)

    lan_ip = detect_lan_ip()

    serial_port = (
        find_serial_port()
    )

    print(
        "\n== AmpPulse AI Status"
    )

    print(
        "  Operating System : "
        f"{platform.system()}"
    )

    print(
        "  Backend          : "
        + (
            f"RUNNING "
            f"http://127.0.0.1:{port}"
            if backend_up
            else
            "NOT RUNNING"
        )
    )

    print(
        "  Frontend         : "
        "http://localhost:5500"
    )

    if lan_ip:

        print(
            f"  Laptop LAN IP    : "
            f"{lan_ip}"
        )

    print(
        "  ESP32 Serial     : "
        + (
            serial_port
            if serial_port
            else "NOT DETECTED"
        )
    )

    print(
        f"  Sketch            : "
        f"{SKETCH_FILE}"
    )

    ssid = sketch.get(
        "WIFI_SSID"
    )

    password = sketch.get(
        "WIFI_PASSWORD"
    )

    if (
        ssid
        and ssid not in
        SKETCH_PLACEHOLDERS[
            "WIFI_SSID"
        ]
    ):

        print(
            f"  Wi-Fi SSID       : "
            f"{ssid}"
        )

    else:

        print(
            "  Wi-Fi SSID       : "
            "NOT CONFIGURED"
        )

    if (
        password
        and password not in
        SKETCH_PLACEHOLDERS[
            "WIFI_PASSWORD"
        ]
    ):

        print(
            "  Wi-Fi Password   : "
            "*****"
        )

    else:

        print(
            "  Wi-Fi Password   : "
            "NOT CONFIGURED"
        )

    print(
        "\n  ESP32 web server:"
    )

    print(
        "    http://<ESP32-IP>/data"
    )


# ================================================================
# Interactive menu
# ================================================================

def menu() -> int:

    print(
        """
  ⚡ AmpPulse AI — Windows ESP32 Setup
  =================================================

  1) FULL AUTO
     Configure Wi-Fi → upload → verify

  2) Configure Wi-Fi credentials

  3) Upload ESP32 code

  4) Run GUI
     Start backend + frontend + browser

  5) Verify ESP32 /data

  6) Show current status

  7) Stop backend + frontend

  8) Install arduino-cli

  9) Quit

  =================================================
"""
    )

    while True:

        try:

            raw = input(
                "Choose option [1-9] "
                "(Enter=4): "
            )

        except (
            KeyboardInterrupt,
            EOFError,
        ):

            print("\nBye!")

            return 0

        choice = (
            raw.strip()
            or "4"
        )

        try:

            if choice == "1":

                configure_sketch()

                if do_upload():

                    ip = prompt_esp32_ip(
                        read_sketch_defines()
                    )

                    verify_esp32(ip)

            elif choice == "2":

                configure_sketch()

            elif choice == "3":

                if not SKETCH_FILE.exists():

                    sys.exit(
                        f"Sketch not found: "
                        f"{SKETCH_FILE}"
                    )

                do_upload()

            elif choice == "4":

                run_gui()

            elif choice == "5":

                ip = prompt_esp32_ip(
                    read_sketch_defines()
                )

                verify_esp32(ip)

            elif choice == "6":

                show_status()

            elif choice == "7":

                stop_servers()

            elif choice == "8":

                cli = install_arduino_cli()

                print(
                    f"arduino-cli ready: "
                    f"{cli}"
                )

            elif choice == "9":

                print("\nBye!")

                return 0

            else:

                print(
                    "Invalid option. "
                    "Enter 1-9."
                )

        except (
            KeyboardInterrupt,
            EOFError,
        ):

            print("\nAborted.")

            return 1

        except SystemExit as exc:

            print(
                f"\nStopped: {exc}"
            )

        except Exception as exc:

            print(
                f"\nError: {exc}"
            )

        print()


# ================================================================
# Main
# ================================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "AmpPulse AI Windows ESP32 setup"
        )
    )

    parser.add_argument(
        "--menu",
        action="store_true",
        help="Open interactive menu",
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current status",
    )

    parser.add_argument(
        "--gui",
        action="store_true",
        help="Start backend + frontend",
    )

    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop backend + frontend",
    )

    parser.add_argument(
        "--ssid",
        help="Wi-Fi SSID",
    )

    parser.add_argument(
        "--password",
        help="Wi-Fi password",
    )

    parser.add_argument(
        "--esp32-ip",
        help="ESP32 IP address",
    )

    parser.add_argument(
        "--port",
        help="ESP32 COM port, e.g. COM5",
    )

    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Configure sketch but don't upload",
    )

    parser.add_argument(
        "--install-cli",
        action="store_true",
        help="Install arduino-cli automatically",
    )

    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip ESP32 verification",
    )

    args = parser.parse_args()

    # ------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------

    if (
        args.menu
        or len(sys.argv) == 1
    ):

        return menu()

    # ------------------------------------------------------------
    # Status
    # ------------------------------------------------------------

    if args.status:

        show_status()

        return 0

    # ------------------------------------------------------------
    # GUI
    # ------------------------------------------------------------

    if args.gui:

        ensure_env_secrets(
            read_env()
        )

        run_gui()

        return 0

    # ------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------

    if args.stop:

        stop_servers()

        return 0

    # ------------------------------------------------------------
    # One-shot setup
    # ------------------------------------------------------------

    ensure_env_secrets(
        read_env()
    )

    configure_sketch(
        ssid_arg=args.ssid,
        password_arg=args.password,
    )

    uploaded = False

    if args.skip_upload:

        print(
            "\nUpload skipped."
        )

        print(
            "Open the sketch in Arduino IDE "
            "and press Upload."
        )

    else:

        uploaded = do_upload(
            args.port,
            install_arg=args.install_cli,
        )

    if (
        uploaded
        and not args.no_verify
    ):

        ip = prompt_esp32_ip(
            read_sketch_defines(),
            args.esp32_ip,
        )

        verify_esp32(ip)

    print(
        "\n================================================"
    )

    print(
        "Next:"
    )

    print(
        "  python setup_esp32.py --gui"
    )

    print(
        "or open:"
    )

    print(
        "  http://localhost:5500"
    )

    print(
        "\nLogin:"
    )

    print(
        "  demo@amppulse.ai"
    )

    print(
        "  Demo@12345"
    )

    print(
        "\nThen enter the ESP32 IP in "
        "the ESP32 Connect bar."
    )

    print(
        "================================================"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
