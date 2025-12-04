#!/usr/bin/env python3
import subprocess
import json
import socket
import ipaddress
import requests
from flask import Flask, jsonify

app = Flask(__name__)

SCAN_PORT = int("9999")
SCAN_TIMEOUT = 0.2

def get_local_ip():
    """Obtain local IP by opening UDP socket."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip

def get_subnet(ip):
    """Get subnet from system routing."""
    result = subprocess.check_output(["ip", "route"]).decode()

    for line in result.splitlines():
        if ip in line:
            parts = line.split()
            for part in parts:
                if "/" in part:
                    return ipaddress.ip_network(part, strict=False)

    # fallback
    return ipaddress.ip_network(f"{ip}/24", strict=False)

def adjust_subnet(net):
    """Reduce huge networks automatically."""
    if net.prefixlen <= 20:  # /8 /16 /20
        # Reduce to /24
        network = ipaddress.ip_network(f"{list(net.hosts())[0]}/24", strict=False)
        return network
    return net

def scan_host(ip):
    """Check if /prom-targets is alive."""
    url = f"http://{ip}:{SCAN_PORT}/prom-targets"
    try:
        r = requests.get(url, timeout=SCAN_TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

@app.route("/sd")
def service_discovery():
    local_ip = get_local_ip()
    subnet = get_subnet(local_ip)
    subnet = adjust_subnet(subnet)

    print(f"[DISCOVERY] Local IP: {local_ip}")
    print(f"[DISCOVERY] Scanning subnet: {subnet}")

    results = []

    for ip in subnet.hosts():
        data = scan_host(str(ip))
        if data:
            print(f"[DISCOVERY] Found active device-info at {ip}")
            results.extend(data)

    return jsonify(results)

app.run(host="0.0.0.0", port=8000)
