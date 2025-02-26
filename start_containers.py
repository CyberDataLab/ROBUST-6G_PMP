#!/usr/bin/env python3
import subprocess

def main():

    try:
        mid = subprocess.check_output(
            ["python3", "./machine_id/machine_id.py"],
            text=True
        ).strip()
    except subprocess.CalledProcessError as e:
        print(f"Error al ejecutar machine_id.py: {e}")
        return

    with open(".env", "w", encoding="utf-8") as f:
        f.write(f"MACHINE_ID={mid}\n")
    #print(f"Generado fichero .env con MACHINE_ID={mid}")

    try:
        subprocess.run(["docker-compose", "up", "-d"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error al ejecutar docker-compose: {e}")
        return

if __name__ == "__main__":
    main()
