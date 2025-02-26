#!/usr/bin/env python3
import subprocess

def main():

    try:
        mid = subprocess.check_output(
            ["python3", "./machine_id/machine_id.py"],
            text=True
        ).strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing machine_id.py: {e}")
        return

    with open(".env", "w", encoding="utf-8") as f:
        f.write(f"MACHINE_ID={mid}\n")

    try:
        subprocess.run(["docker-compose", "up", "-d"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing docker-compose: {e}")
        return

if __name__ == "__main__":
    main()
