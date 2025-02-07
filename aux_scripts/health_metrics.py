#!/usr/bin/env python3
import psutil

def main():
    # "Calentar" la medición de CPU
    psutil.cpu_percent(interval=None)  # sin usar el valor
    cpu_usage = psutil.cpu_percent(interval=1)  # segunda llamada, valor real
    mem_info = psutil.virtual_memory().available / (1024*1024)  # en MB
    print(f'{{"cpu_usage":{cpu_usage},"memory_mb":{mem_info}}}')

if __name__ == "__main__":
    main()
