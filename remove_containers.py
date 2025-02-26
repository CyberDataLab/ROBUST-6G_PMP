import subprocess

def ejecutar_comando(comando):
    try:
        resultado = subprocess.run(comando, shell=True, check=True, text=True, capture_output=True)
        print(f"Comando ejecutado con éxito: {comando}")
        print(f"Salida: {resultado.stdout}")
    except subprocess.CalledProcessError as e:
        print(f"Error al ejecutar el comando {comando}: {e}")
        print(f"Salida de error: {e.stderr}")

if __name__ == "__main__":
    comandos = [
        "docker kill kafka fluentd filebeat telegraf",
        "docker container prune -f",  # -f para evitar la confirmación interactiva
        "docker volume prune -f",      # -f para evitar la confirmación interactiva
        "rm -r data/"
    ]

    for comando in comandos:
        ejecutar_comando(comando)
