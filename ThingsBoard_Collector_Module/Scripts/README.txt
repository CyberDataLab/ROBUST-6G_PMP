Ciao a tutti, Alberto here, follow these steps to check if the entire PMP is working correctly.

First of all, I know this is just a test to collect information from ThingsBoard devices, but here is the current complete PMP (as of February 6, 2026). I mention this because there is no Configuration Manager yet, but I use a launcher to simulate the functionality of Security Orchestrator. With these steps, you can deploy the containers, test the API using a Python script, and collect alarms from Kafka topics.
Send me a message if you have any problems, see an error, or anything like that. -> alberto.garciap@um.es

1. Installing requirements:
    1.1. sudo apt-get install Kafkacat
    1.2. pip install request

2. Modify the DNS to include the Kafka broker associated with the IP (192.168.40.252 I guess):
    2.1. sudo nano /etc/hosts (use vim if you don't have nano)
    2.2. private_ip  kafka_robust6g-node1.lan

3. Clone the repository :
    3.1. git clone https://github.com/CyberDataLab/ROBUST-6G_PMP.git

4. Move, start the PMP (only the API for ThingsBoard and the Kafka communication bus) and check if the containers are working correctly:
    4.1. cd ROBUST-6G_PMP
    4.2. python3 Launcher/bootstrap_gui_backend.py --skip-api --skip-gui
    4.3. sudo python3 ./Launcher/start_containers.py -m thingsboard_module -t all
    4.4. sudo docker logs thingsboard_collector_robust6g

5. Launch the test and consume topics from the communication bus with Kafkacat:
    5.1. python3 ./ThingsBoard_Collector_Module/Scripts/test.py
    5.2. kafkacat -b kafka_robust6g-node1.lan:9094 -G tb_consumer_group '^thingsboard_.*'
    5.3. Generate alarms when script said please.
    5.4. Check the output and the output terminal of the Kafkacat

6. Stop PMP containers if you want:
    6.1. python3 Launcher/stop_gui_backend.py --stop-api-tools
