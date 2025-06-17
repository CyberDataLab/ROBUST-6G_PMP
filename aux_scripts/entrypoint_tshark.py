#!/usr/bin/env python3

import subprocess
import sys
import os
import time
import signal
import re

# Configuración
LOG_PATH = "/data/traces/infile.json"
ROTATED_PATH = LOG_PATH + ".backup"
SIZE_LIMIT = 30 * 1024 * 1024  # 30 MB

def get_interfaces():
    try:
        result = subprocess.run(
            ["/usr/bin/python3", "/usr/local/bin/search_interface.py"],
            capture_output=True, text=True, check=True
        )
        interfaces = result.stdout.strip().split()
    except subprocess.CalledProcessError:
        print("ERROR 1: No se encontraron interfaces activas", file=sys.stderr)
        sys.exit(1)

    if not interfaces:
        print("ERROR 2: No se encontraron interfaces activas", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Usando interfaces: {', '.join(interfaces)}")
    return interfaces

def build_tshark_command(interfaces):
    command = ["tshark"]
    for interface in interfaces:
        new_interface = re.findall(r"'(.*?)'", interface)
        command.extend(["-i", new_interface[0]])
    command.extend(["-T", "json", "-x", "--no-duplicate-keys"])
    return command

def run_tshark(command):
    output_file = open(LOG_PATH, "w")
    print("[*] Iniciando tshark...")
    return subprocess.Popen(command, stdout=output_file), output_file

def monitor_and_rotate(command, proc, output_file):
    while True:
        time.sleep(5)
        if os.path.exists(LOG_PATH):
            size = os.path.getsize(LOG_PATH)
            if size >= SIZE_LIMIT:
                print(f"[!] Log alcanzó {size / (1024 * 1024):.2f} MB, rotando...")

                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

                output_file.close()

                if os.path.exists(ROTATED_PATH): #Mantiene un backup de la ultima rotación
                    os.remove(ROTATED_PATH)
                os.rename(LOG_PATH, ROTATED_PATH)
                open(LOG_PATH, 'w').close()

                proc, output_file = run_tshark(command)
        else:
            print("[!] Fichero de log no existe, recreando...")
            open(LOG_PATH, 'w').close()

        time.sleep(5)

def main():
    interfaces = get_interfaces()
    command = build_tshark_command(interfaces)
    proc, output_file = run_tshark(command)
    try:
        monitor_and_rotate(command, proc, output_file)
    except KeyboardInterrupt:
        print("[*] Terminando por interrupción...")
        proc.terminate()
        proc.wait()
        output_file.close()

if __name__ == "__main__":
    main()
