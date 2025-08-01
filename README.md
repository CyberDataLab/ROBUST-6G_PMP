<h1 align="center">PMP (Programmable Monitoring Platform)</h1>

PMP is an open source, modularly designed, programmable platform for collecting, exposing and visualising data from data sources in the Contiuum Cloud. In addition, it provides threat detection to alert and notify on anomalous behaviour by analysing network traffic. Finally, PMP uses agnostic Sigma rules to configure the tools.

![Framework](https://github.com/CyberDataLab/ROBUST-6G_PMP/blob/main/PMP_design.pdf)


## 🔧 Features

 - :cyclone: **Data collection in real time**
 - :electric_plug: **Automatisation process**
 - :bell: **Alerts and notifications**
 - :hammer: **Dynamic configuration**
 - :bar_chart: **Data visualisation**
 - :heavy_plus_sign: **Modular**
 - 🚀 **RESTful Public API for programmatic access**
 - 🐳 **Dockerized deployment for easy setup**  

## :nut_and_bolt: Tools

:lock: Developed
 * Fluentd
 * Telegraf
 * Falco
 * Tshark
 * Filebeat
 * Kafka

:construction: Future development
 * Snort3
 * Grafana
 * Kibana
 * Elasticsearch
 * InfluxDB
 * Sigma translator

## ⚙️ Installation

1. **Clone** the repository:
   ```bash
   gh repo clone CyberDataLab/ROBUST-6G_PMP
    ```
2. **Navigate** to the project directory:
    ```bash
    cd ROBUST-6G_PMP/
    ```

3. **Generate modified images**
    ```bash
    sudo docker build -f Dockerfiles/dockerfile.falco -t falco_robust6g:latest .
    sudo docker build -f Dockerfiles/dockerfile.fluentd -t fluentd_robust6g:latest .
    sudo docker build -f Dockerfiles/dockerfile.tshark -t tshark_robust6g:latest .
    ```


## 🕹️ Usage


1. **Permissions** of Filebeat configuration
    ```bash
    sudo chmod 644 configuration_files/filebeat.yml
    sudo chown root:root configuration_files/filebeat.yml
    ```

2. **Usage and deployment** using 
    ```bash
    python3 start_containers.py
    ```

Do not use the `docker-compose.yml` file because the PMP needs an environment variable to uniquely identify the machine using the monitoring tools.

3. **Delete** containers and deployed volumes as well as generated data at the same time.
    ```bash
    python3 remove_containers.py
    ```

## 📋 Requirements

 * `Docker` 27.5.1 or higher.
 * `docker-compose` 1.29.2 or higher.
 * `Python3.12` or higher.

The tool containers already satisfy their requirements without the need of any user installation.

## 📜 License

PMP is **open-source** under the **GPL-3.0 license**. See the `LICENSE` file for details.

## :heavy_exclamation_mark: Errors

In case `filebeat.yml` is showing errors, change the permissions with: 
```bash
    sudo chmod 644 filebeat.yml
    sudo chown root:root filebeat.yml
``` 
