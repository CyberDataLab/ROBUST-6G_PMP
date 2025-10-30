<h1 align="center">PMP (Programmable Monitoring Platform)</h1>

PMP is an open source, modularly designed, programmable platform for collecting, exposing and visualising data from data sources in the Contiuum Cloud. In addition, it provides threat detection to alert and notify on anomalous behaviour by analysing network traffic. Finally, PMP uses agnostic Sigma rules to configure the tools.

![Framework](https://github.com/CyberDataLab/ROBUST-6G_PMP/blob/main/PMP_design.svg)


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
 * Snort3
 * MongoDB
 * CICFlowMeter

:construction: Future development
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
    sudo docker build -f ./Alert_Module/Docker/Dockerfiles/alert_module.dockerfile -t alert_module_novadef:latest .
    sudo docker build -f ./Data_Collection_Module/Docker/Dockerfiles/falco.dockerfile -t falco_novadef:latest .
    sudo docker build -f ./Data_Collection_Module/Docker/Dockerfiles/fluentd.dockerfile -t fluentd_novadef:latest .
    sudo docker build -f ./Data_Collection_Module/Docker/Dockerfiles/tshark.dockerfile -t tshark_novadef:latest .
    sudo docker build -f ./Flow_Module/Docker/Dockerfiles/flow_module.dockerfile -t flow_module_novadef:latest .
    ```


## 🕹️ Usage


1. **Permissions** of Filebeat configuration
    ```bash
    sudo chmod 644 configuration_files/filebeat.yml
    sudo chown root:root configuration_files/filebeat.yml
    ```

2. **Usage and deployment** as a general option in which all modules are activated.
    ```bash
    python3 ./Launcher/start_containers.py all
    ```
3. **Usage and deplyment** exploiting the modularity of PMP. Use `-m` to name each **module** followed by `-t` with the simple name of the **tools** to be deployed. Tools can be concatenated using **spaces** or **commas**. If you need to use **all the tools** in the module, you can use `-t all`.
    ```bash
    sudo python3 ./Launcher/start_containers.py -m moduleName -t all
    ```
    Or
    ```bash
    sudo python3 ./Launcher/start_containers.py -m moduleName -t toolName1,toolName2
    ```
    In example
    ```bash
    sudo python3 ./Launcher/start_containers.py -m alert_module -t all -m db_module -t all -m communication_module -t all -m flow_module -t all -m collection_module -t tshark,fluentd,telegraf
    ```

Do not use the `docker-compose.yml` file, as the PMP requires an environment file to run correctly.

4. **Delete** containers and deployed volumes as well as generated data at the same time.
    ```bash
    python3 ./Launcher/remove_containers.py
    ```

## :notebook: Notes
Table of current modules and tools implemented.

|        Modules       |    Tool 1    |  Tool 2  |  Tool 3 |  Tool 4 |
|:--------------------:|:------------:|:--------:|:-------:|:-------:|
|     alert_module     | alert_module |          |         |         |
| communication_module |     kafka    | filebeat |         |         |
|   collection_module  |    fluentd   | telegraf |  tshark |  falco  |
|      flow_module     |  flow_module |          |         |         |
|       db_module      |    mongodb   |          |         |         |


## 📋 Requirements

 * `Docker` 28.5.1 or higher.
 * ~~`docker-compose` 1.29.2 or higher.~~ Please do not use the individual docker-compose module. Docker 28.5.1 or higher utilises the updated version of `docker compose`, which has the appropriate functionalities to run the PMP.
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

If you are using PMP as a test on your local machine, remember to update the `/etc/hosts` file to avoid issues with DNS addressing on Kafka brokers. In example:

    ```bash
    sudo nano /etc/hosts
    ```
Write the following line below the `127.0.1.1       user`:
    ```bash
	yourIP	kafka_robust6g-node1.lan
    ```