#sudo docker build -f dockerfile_alert_module.dockerfile -t alert_module_robust6g:latest .
FROM ubuntu:jammy

RUN apt update -y && apt upgrade -y
RUN apt install -y --allow-change-held-packages tshark

RUN mkdir -p /home/Alert_Module/Snort_configuration
# Instalamos dependencias y snort3 mediante un script previo
COPY ./Scripts/snort3_auto_install.sh /home/Alert_Module/Snort_configuration
RUN chmod +x /home/Alert_Module/Snort_configuration/snort3_auto_install.sh 
#/bin/sh -c ruta
RUN  ./home/Alert_Module/Snort_configuration/snort3_auto_install.sh 
#Paquetes para J2P
RUN pip install ijson scapy bitstring 
# Crear carpetas: FIXME -> Si creo ya las carpetas, tendré que quitar del código la creación de éstas. -> Hecho
    #/home/Alert_Module/
        # /home/Alert_Module/Alerts
        # /home/Alert_Module/Snort_configuration/
            #/home/Alert_Module/Snort_configuration/lua -> FIXME seguramente no haga falta si referencio bien la carpeta lua de preinstalada
            #/home/Alert_Module/Snort_configuration/Rules
        # /home/Alert_Module/Parsing/
            # /home/Alert_Module/Parsing/JSON2PCAP
            # /home/Alert_Module/Parsing/PCAP_Files

RUN mkdir -p /home/Alert_Module/Alerts \
    /home/Alert_Module/Snort_configuration/lua \
    /home/Alert_Module/Snort_configuration/Rules \
    /home/Alert_Module/Parsing/JSON2PCAP \
    /home/Alert_Module/Parsing/PCAP_Files

# Copiar entrypoint que es el alert_module_run.py (ajustar rutas de ficheros) en /home
COPY ./Docker/Entrypoints/alert_module_run.py /home/Alert_Module
# Copiar:
    #/home/Snort_configuration/lua/todos los ficheros de lua
    #/home/Snort_configuration/Rules/alert_rules.rules
    #/home/Parsing/JSON2PCAP/todos los ficheros de J2P
COPY ./Configuration_Files/lua/. /home/Alert_Module/Snort_configuration/lua
COPY ./Configuration_Files/Rules/. /home/Alert_Module/Snort_configuration/Rules
COPY ./Scripts/JSON2PCAP/. /home/Alert_Module/Parsing/JSON2PCAP/ 
# De momento podría incluir la instalación de Tshark para seguir usando Tshark como fuente de entrada inicial.
    # Instalar Tshark -> FIXME no será necesario en la versión final porque se sustituye por un consumer de Kafka



ENTRYPOINT ["/usr/bin/python3","/home/Alert_Module/alert_module_run.py"]