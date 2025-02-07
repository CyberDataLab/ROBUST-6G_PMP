# PMP_Docker
Integration of Fluentd, Telegraf, Snort, Falco with Filebeat and Kafka as communicators.

Please, to run the PMP do not type “sudo docker compose up -d”, use the script named “start_containers.sh” because the PMP needs an environment variable to uniquely identify the machine using the monitoring tools. So run with "sudo ./start_containers.sh". Check the execution permission of this file, in case that doesn't have the execution permision, write "sudo chmod +x start_containers.sh".
