import platform
import subprocess
import sys

def get_device_id():
    system_name = platform.system().lower()
    if system_name == "windows":
        mid_binary = "./machine_id/mid_windows/mid.exe"
    else:
        mid_binary = "./machine_id/mid_linux_macos/mid"

    try:
        output = subprocess.check_output([mid_binary], stderr=subprocess.STDOUT)
        device_id = output.decode("utf-8").strip()
        return device_id
    except FileNotFoundError:
        print(f"Binary not found '{mid_binary}'.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error while executing '{mid_binary}': {e.output.decode('utf-8')}")
        sys.exit(1)

if __name__ == "__main__":
    device_id = get_device_id()
    print(f"{device_id}")