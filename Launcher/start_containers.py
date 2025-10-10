#!/usr/bin/env python3

import subprocess
import platform
import sys
from pathlib import Path

def detect_os():
    system = platform.system().lower()
    print(f"Detected OS: {system}")
    if system == "linux":
        return "host"
    elif system == "windows" or system == "darwin":
        return "bridge"
    else:
        return "error"

def main():
    try:
        
        LFD = Path(__file__).resolve().parent # Launcher Folder Directory
        mid_py = LFD / "machine_id" / "machine_id.py"
        mid = subprocess.check_output(
            [sys.executable, str(mid_py)],
            text=True
        ).strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing machine_id.py: {e}")
        return

    network_mode = detect_os()

    # Guardar .env en el mismo directorio del script (robusto ante cwd distintos)
    PFD = Path(__file__).resolve().parent.parent # Project Folder Directory
    with open(LFD / ".env", "w", encoding="utf-8") as f:
        f.write(f"MACHINE_ID={mid}\n")
        f.write(f"NETWORK_MODE={network_mode}\n")
        f.write(f"PFD={PFD}\n") 

    try:
        # Mantengo el fichero de compose que usas en pruebas ("test-compose.yml") como pediste.

        subprocess.run(["docker-compose","-f", f"{str(LFD)}/docker-compose.yml" , "up", "-d"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing docker-compose: {e}")
        return

if __name__ == "__main__":
    main()