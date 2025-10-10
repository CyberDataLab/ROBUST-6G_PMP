#!/usr/bin/env python3

import subprocess
import sys
import os
import time
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

LOG_PATH = "/data/traces/infile.json"
ROTATED_PATH = LOG_PATH + ".backup"
SIZE_LIMIT = 30 * 1024 * 1024  # 30 MB

def get_interfaces():
    try:
        # Ejecutar el script local search_interface.py con el mismo intérprete Python
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "search_interface.py")],
            capture_output=True, text=True, check=True
        )
        interfaces = result.stdout.strip().split()
    except subprocess.CalledProcessError:
        print("ERROR 1: No active interfaces were found", file=sys.stderr)
        sys.exit(1)

    if not interfaces:
        print("ERROR 2: No active interfaces were found", file=sys.stderr)
        sys.exit(1)
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
    return subprocess.Popen(command, stdout=output_file), output_file

def monitor_and_rotate(command, proc, output_file):
    while True:
        time.sleep(5)
        if os.path.exists(LOG_PATH):
            size = os.path.getsize(LOG_PATH)
            if size >= SIZE_LIMIT:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

                output_file.close()

                if os.path.exists(ROTATED_PATH):
                    os.remove(ROTATED_PATH)
                os.rename(LOG_PATH, ROTATED_PATH)
                open(LOG_PATH, 'w').close()

                proc, output_file = run_tshark(command)
        else:
            print("Log file does not exist, re-creating it")
            open(LOG_PATH, 'w').close()

        time.sleep(5)

def main():
    interfaces = get_interfaces()
    command = build_tshark_command(interfaces)
    proc, output_file = run_tshark(command)
    try:
        monitor_and_rotate(command, proc, output_file)
    except KeyboardInterrupt:
        print("Ending by interruption")
        proc.terminate()
        proc.wait()
        output_file.close()

if __name__ == "__main__":
    main()
