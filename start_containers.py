#!/usr/bin/env python3

import subprocess
import platform

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
        mid = subprocess.check_output(
            ["python3", "./machine_id/machine_id.py"],
            text=True
        ).strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing machine_id.py: {e}")
        return

    network_mode = detect_os()

    with open(".env", "w", encoding="utf-8") as f:
        f.write(f"MACHINE_ID={mid}\n")
        f.write(f"NETWORK_MODE={network_mode}\n")

    try:
        subprocess.run(["docker-compose", "up", "-d"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing docker-compose: {e}")
        return

if __name__ == "__main__":
    main()