#!/usr/bin/env python3
import os
from flask import Flask, jsonify

app = Flask(__name__)

machine_id = os.getenv("MACHINE_ID", "unknown")

# Services running. 0 is for not running and 1 is for running. If not env var, then default is 0.
enable_telegraf = os.getenv("ENABLE_TELEGRAF", "0") == "1"
enable_fluentd = os.getenv("ENABLE_FLUENTD", "0") == "1"
enable_falco_exporter = os.getenv("ENABLE_FALCO", "0") == "1"


@app.route("/prom-targets")
def prom_targets():
    targets = []

    if enable_telegraf:
        telegraf_address="localhost:"+os.getenv("TELEGRAF_TO_PROMETHEUS_PORT")
        targets.append(telegraf_address) 
    if enable_fluentd:
        fluentd_address="localhost:"+os.getenv("FLUENTD_TO_PROMETHEUS_PORT")
        targets.append(fluentd_address)
    if enable_falco_exporter:
        falco_exporter_address="localhost:"+os.getenv("FALCO_EXPORTER_PORT")
        targets.append(falco_exporter_address)

    return jsonify([
        {
            "targets": targets,
            "labels": {
                "machine_id": machine_id
            }
        }
    ])

app.run(host="0.0.0.0", port=int(os.getenv("DEVICE_INFO_PORT")))
