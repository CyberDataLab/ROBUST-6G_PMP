import subprocess

def execute_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        print(f"Command executed successfully: {command}")
        print(f"Output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        print(f"Error executing the command {command}: {e}")
        print(f"Error output: {e.stderr}")

if __name__ == "__main__":
    command_list = [
        "docker kill kafka fluentd filebeat telegraf",
        "docker container prune -f", 
        "docker volume prune -f",
        "rm -r data/"
    ]

    for command in command_list:
        execute_command(command)
