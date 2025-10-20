from pathlib import Path
import subprocess

def executing_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        print(f"Result of {command}: \n {result.stdout}")
    except subprocess.CalledProcessError as e:
        print(f"Error executing the command {command}: {e}")
        print(f"Error output: {e.stderr}")

if __name__ == "__main__":
    #docker stop $(docker ps -a -q), docker rm $(docker ps -a -q) insted of docker kill
    PFD = Path(__file__).resolve().parent.parent # Project Folder Directory
    command_list = [
        "docker kill kafka fluentd filebeat telegraf tshark falco alert_module mongodb", 
        "docker container prune -f",
        "docker volume prune -f",
        f"rm -r {PFD}/Results/"
    ]

    for command in command_list:
        executing_command(command)
