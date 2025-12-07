#!/usr/bin/env python3
"""
Job Tracker - Easy Installer
============================
This script sets up everything you need to run Job Tracker.
Just run: python install.py
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header():
    print(f"""
{Colors.BLUE}{Colors.BOLD}
     ╦╔═╗╔╗   ╔╦╗╦═╗╔═╗╔═╗╦╔═╔═╗╦═╗
     ║║ ║╠╩╗   ║ ╠╦╝╠═╣║  ╠╩╗║╣ ╠╦╝
    ╚╝╚═╝╚═╝   ╩ ╩╚═╩ ╩╚═╝╩ ╩╚═╝╩╚═
{Colors.END}
    Easy Installer for Job Tracker
    ===============================
    """)

def print_step(step, message):
    print(f"{Colors.BLUE}[{step}]{Colors.END} {message}")

def print_success(message):
    print(f"{Colors.GREEN}✓{Colors.END} {message}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠{Colors.END} {message}")

def print_error(message):
    print(f"{Colors.RED}✗{Colors.END} {message}")

def check_python_version():
    """Check if Python version is 3.9+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print_error(f"Python 3.9+ required. You have {version.major}.{version.minor}")
        print("Please install a newer version of Python from https://python.org")
        return False
    print_success(f"Python {version.major}.{version.minor} detected")
    return True

def create_virtual_environment():
    """Create a virtual environment if it doesn't exist."""
    venv_path = Path("venv")
    if venv_path.exists():
        print_success("Virtual environment already exists")
        return True

    print_step("2", "Creating virtual environment...")
    try:
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        print_success("Virtual environment created")
        return True
    except subprocess.CalledProcessError:
        print_error("Failed to create virtual environment")
        return False

def get_pip_command():
    """Get the correct pip command for the virtual environment."""
    if sys.platform == "win32":
        return str(Path("venv/Scripts/pip.exe"))
    return str(Path("venv/bin/pip"))

def get_python_command():
    """Get the correct python command for the virtual environment."""
    if sys.platform == "win32":
        return str(Path("venv/Scripts/python.exe"))
    return str(Path("venv/bin/python"))

def run_with_progress(command, description):
    """Run a command with a spinning progress indicator."""
    import threading
    import time
    import itertools

    spinner = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
    done = False

    def spin():
        while not done:
            sys.stdout.write(f'\r  {next(spinner)} {description}...')
            sys.stdout.flush()
            time.sleep(0.1)

    # Start spinner in background
    spinner_thread = threading.Thread(target=spin)
    spinner_thread.start()

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        done = True
        spinner_thread.join()
        sys.stdout.write(f'\r  {Colors.GREEN}✓{Colors.END} {description}   \n')
        sys.stdout.flush()
        return True, result
    except subprocess.CalledProcessError as e:
        done = True
        spinner_thread.join()
        sys.stdout.write(f'\r  {Colors.RED}✗{Colors.END} {description} - Failed\n')
        sys.stdout.flush()
        return False, e

def install_dependencies():
    """Install required packages with progress indicators."""
    print_step("3", "Installing dependencies...")
    print()
    pip = get_pip_command()
    python = get_python_command()

    # Upgrade pip using python -m pip (avoids Windows locking issues)
    success, _ = run_with_progress(
        [python, "-m", "pip", "install", "--upgrade", "pip"],
        "Upgrading pip to latest version"
    )
    if not success:
        print_warning("Pip upgrade failed, continuing anyway...")

    # Upgrade setuptools and wheel for better compatibility
    success, _ = run_with_progress(
        [python, "-m", "pip", "install", "--upgrade", "setuptools", "wheel"],
        "Upgrading setuptools and wheel"
    )
    if not success:
        print_warning("Setuptools upgrade failed, continuing anyway...")

    # Install requirements
    success, result = run_with_progress(
        [pip, "install", "-r", "requirements.txt"],
        "Installing application packages"
    )

    if success:
        print()
        print_success("All dependencies installed successfully!")
        return True
    else:
        print()
        print_error("Failed to install dependencies")
        if hasattr(result, 'stderr') and result.stderr:
            print(result.stderr)
        return False

def setup_directories():
    """Create necessary directories."""
    print_step("4", "Setting up directories...")

    dirs = ["data", "data/resumes", "config", "app/static", "app/static/css", "app/static/js"]
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    print_success("Directories created")
    return True

def setup_config():
    """Set up configuration files."""
    print_step("5", "Setting up configuration...")

    env_path = Path("config/.env")
    env_example = Path("config/.env.example")

    if not env_path.exists() and env_example.exists():
        shutil.copy(env_example, env_path)
        print_success("Created config/.env from template")
    elif not env_path.exists():
        # Create a basic .env file
        with open(env_path, 'w') as f:
            f.write("# Job Tracker Configuration\n")
            f.write("# Add your OpenAI API key for email classification (optional)\n")
            f.write("# OPENAI_API_KEY=your-key-here\n")
        print_success("Created config/.env")
    else:
        print_success("Configuration file exists")

    return True

def create_start_script():
    """Create easy start scripts for different platforms."""
    print_step("6", "Creating start scripts...")

    # Unix/Mac start script
    unix_script = """#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
echo ""
echo "Starting Job Tracker..."
echo "Open http://localhost:8000 in your browser"
echo "Press Ctrl+C to stop"
echo ""
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

    with open("start.sh", 'w') as f:
        f.write(unix_script)
    os.chmod("start.sh", 0o755)

    # Windows start script
    windows_script = """@echo off
cd /d "%~dp0"
call venv\\Scripts\\activate.bat
echo.
echo Starting Job Tracker...
echo Open http://localhost:8000 in your browser
echo Press Ctrl+C to stop
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
"""

    with open("start.bat", 'w') as f:
        f.write(windows_script)

    print_success("Created start.sh (Mac/Linux) and start.bat (Windows)")
    return True

def get_local_ip():
    """Get the local IP address for network access."""
    import socket
    try:
        # Connect to an external address to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

def print_next_steps():
    """Print instructions for the user."""
    python_cmd = get_python_command()
    local_ip = get_local_ip()

    # Build the phone access section
    if local_ip:
        phone_section = f"""
{Colors.BOLD}Access from your phone:{Colors.END}

  Open {Colors.BLUE}http://{local_ip}:8000{Colors.END} on your phone
  (Make sure you're on the same WiFi network)"""
    else:
        phone_section = f"""
{Colors.BOLD}Access from your phone:{Colors.END}

  Find your computer's IP address and open:
  http://YOUR_IP:8000 on your phone's browser
  (Make sure you're on the same WiFi network)"""

    print(f"""
{Colors.GREEN}{Colors.BOLD}Installation Complete!{Colors.END}
{Colors.GREEN}======================{Colors.END}

{Colors.BOLD}To start Job Tracker:{Colors.END}

  Mac/Linux:  ./start.sh
  Windows:    start.bat

  Or manually: {python_cmd} -m uvicorn app.main:app --host 0.0.0.0 --port 8000

{Colors.BOLD}Then open:{Colors.END} {Colors.BLUE}http://localhost:8000{Colors.END}

{Colors.BOLD}Optional Setup:{Colors.END}

  1. Gmail Sync: Add your Gmail API credentials to config/
     - See the Email Sync page for instructions

  2. AI Classification: Add your OpenAI API key to config/.env
     - Get a key at https://platform.openai.com/api-keys
{phone_section}

{Colors.YELLOW}Need help?{Colors.END} Visit the Email Sync page for setup guides.
""")

def main():
    print_header()

    # Change to script directory
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)

    print_step("1", "Checking Python version...")
    if not check_python_version():
        return 1

    if not create_virtual_environment():
        return 1

    if not install_dependencies():
        return 1

    if not setup_directories():
        return 1

    if not setup_config():
        return 1

    if not create_start_script():
        return 1

    print_next_steps()
    return 0

if __name__ == "__main__":
    sys.exit(main())
