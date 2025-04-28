import subprocess

def executing_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        print(f"Result of {command}: {result.stdout}")
    except subprocess.CalledProcessError as e:
        print(f"Error executing the command {command}: {e}")
        print(f"Error output: {e.stderr}")

if __name__ == "__main__":
    #docker stop $(docker ps -a -q), docker rm $(docker ps -a -q) insted of docker kill
    command_list = [
        "docker kill kafka fluentd filebeat telegraf tshark", 
        "docker container prune -f",
        "docker volume prune -f",
        "rm -r data/"
    ]

    for command in command_list:
        executing_command(command)