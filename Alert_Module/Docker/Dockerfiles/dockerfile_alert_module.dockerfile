#sudo docker build -f ./Alert_Module/Docker/Dockerfiles/dockerfile_alert_module.dockerfile -t alert_module_robust6g:latest .
FROM ubuntu:jammy

RUN mkdir -p /home/Alert_Module/Snort_configuration

# Installing dependencies and snort3 using a pre-existing script
COPY ./Alert_Module/Scripts/snort3_auto_install.sh /home/Alert_Module/Snort_configuration
RUN chmod +x /home/Alert_Module/Snort_configuration/snort3_auto_install.sh 
RUN  ./home/Alert_Module/Snort_configuration/snort3_auto_install.sh

# Requirements
RUN pip install ijson scapy bitstring confluent-kafka pymongo

RUN mkdir -p /home/Alert_Module/Alerts \
    /home/Alert_Module/Snort_configuration/lua \
    /home/Alert_Module/Snort_configuration/Rules \
    /home/Alert_Module/Parsing/JSON2PCAP \
    /home/Alert_Module/Parsing/PCAP_Files

COPY ./Alert_Module/Docker/Entrypoints/alert_module_run.py /home/Alert_Module
COPY ./Alert_Module/Scripts/kafka_io.py /home/Alert_Module/
COPY ./Alert_Module/Configuration_Files/lua/. /home/Alert_Module/Snort_configuration/lua
COPY ./Alert_Module/Configuration_Files/Rules/. /home/Alert_Module/Snort_configuration/Rules
COPY ./Alert_Module/Scripts/JSON2PCAP/. /home/Alert_Module/Parsing/JSON2PCAP/ 


ENTRYPOINT ["/usr/bin/python3","/home/Alert_Module/alert_module_run.py"]