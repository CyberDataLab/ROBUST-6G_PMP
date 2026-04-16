import subprocess
import sys
from pathlib import Path
from typing import Dict, List

MODULE_COMPOSE_FILES: Dict[str, List[str]] = {
    "communication_module": [
        "Communication_Bus/Docker/communication_bus_compose.yml",
    ],
    "alert_module": [
        "Alert_Module/Docker/alert_module_compose.yml",
    ],
    "collection_module": [
        "Data_Collection_Module/Docker/data_collection_module_compose.yml",
    ],
    "flow_module": [
        "Flow_Module/Docker/flow_module_compose.yml",
    ],
    "db_module": [
        "Databases_module/Docker/db_module_compose.yml",
    ],
    "aggregation_module": [
        "Aggregation_Normalisation_Module/Docker/aggregation_normalisation_compose.yml",
    ],
    "thingsboard_module": [
        "ThingsBoard_Collector_Module/Docker/thingsboard_collector_compose.yml",
    ],
}




def remove_containers():
    """
    Stops and removes containers, networks, and volumes for the active profiles defined in the .env file.
    """
    launcher_dir = Path(__file__).parent.resolve()
    env_file = launcher_dir / ".env"
    project_dir = launcher_dir.parent.resolve()

    if not env_file.exists():
        print(f"⚠️  .env file not found in: {launcher_dir}")
        print("   Cannot determine PFD variables or active profiles. Aborting safety.")
        sys.exit(1)

    print(f"🧹 Starting complete cleanup (Containers + Networks + Volumes)...")
    print(f"   (Using configuration from: {env_file})")
      

    cmd = [
        "docker", "compose"
    ]
    for module in MODULE_COMPOSE_FILES.values():
        for path in module: #.get(module, [])
            cmd.extend(["-f", str((project_dir / path).resolve())])
    
    cmd.extend ([
        "--project-directory", str(project_dir),
        "--env-file", str(env_file),
        "down",
        "--volumes",
        "--remove-orphans"
    ])

    try:
        subprocess.run(cmd, check=True)
        print("\n✅ Cleanup completed successfully.")
        
    except subprocess.CalledProcessError:
        print("\n❌ Error: Cleanup failed. Please check your docker permissions.")
        sys.exit(1)

if __name__ == "__main__":
    remove_containers()