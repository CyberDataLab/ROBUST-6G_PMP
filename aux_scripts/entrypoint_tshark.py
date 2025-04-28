#!/usr/bin/env python3

import re
import subprocess
import sys
import threading
import time

def rotate_logs(interval):
    def loop():
        while True:
            time.sleep(interval) # si se supera el tamaño de los logs por defecto se truncaría por lo que es posible que esto vaya fuera
            subprocess.run(["logrotate", "-f", "/etc/logrotate.d/tshark"])
    t = threading.Thread(target=loop, daemon=True)
    t.start()


# Ejecuta el script para obtener la interfaz activa
def main():
    try:
        result = subprocess.run(["/usr/bin/python3", "/usr/local/bin/search_interface.py"], capture_output=True, text=True, check=True)
        interfaces = result.stdout.strip().split()
    except subprocess.CalledProcessError:
        print("ERROR: No se encontraron interfaces activas", file=sys.stderr)
        sys.exit(1)

    if not interfaces:
        print("ERROR: No se encontraron interfaces activas", file=sys.stderr)
        sys.exit(1)

    print(f"Usando interfaces: {', '.join(interfaces)}")

    # Construir el comando con todas las interfaces detectadas
    command = ["tshark"]
    for interface in interfaces:
        new_interface = re.findall("\'(.*?)\'",interface)
        command.extend(["-i", new_interface[0]])

    command.extend(["-T", "json", "-x", "--no-duplicate-keys"]) 

    # Abrir el archivo para escribir la salida
    with open("/data/traces/infile.json", "w") as output_file:
        subprocess.run(command, stdout=output_file)


if __name__ == "__main__":
    rotate_logs(10)  # rota cada 10 segundos si supera el tamaño
    main()
