# PMP_Docker
Integration of Fluentd, Telegraf, Tshark, Falco with Filebeat and Kafka as communicators.

Please, to run the PMP do not type “sudo docker compose up -d”, use the script named “start_containers.py” because the PMP needs an environment variable to uniquely identify the machine using the monitoring tools. So run with "sudo ./start_containers.py".

Check the execution permission of this file, in case that doesn't have the execution permision, write "sudo chmod +x start_containers.py".

In case filebeat.yml is showing errors, change the permissions with: "sudo chmod 644 /configuration_files/filebeat.yml" and "sudo chown root:root /configuration_files/filebeat.yml"
