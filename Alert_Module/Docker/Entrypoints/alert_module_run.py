import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from kafka_io import KafkaLineConsumer, KafkaProducer

# === CONFIG ===
PFD = Path(__file__).resolve().parent #/home/Alert_Module in container

OUTPUT_DIR = str(PFD / "Parsing" / "PCAP_Files")
J2P_PATH = str(PFD / "Parsing" / "JSON2PCAP" /"json2pcap.py")

SNORT_CONFIG_DIR = PFD / "Snort_configuration"
SNORT_LUA = str(SNORT_CONFIG_DIR / "lua" / "snort.lua")
SNORT_RULES = str(SNORT_CONFIG_DIR / "Rules" / "alert_rules.rules")
ALERT_DIR = str(PFD / "Alerts")
ALERT_FILE = "alert_json"

PCAP_ROTATE_SIZE_MB = 2 * 1024 * 1024  # 2 MB
ALERT_ROTATE_SIZE_MB = 200 * 1024 #* 1024 200KB

# === TSHARK CONFIG ===
#TSHARK_INTERFACE = "enp0s3"

# === KAFKA CONFIG ===
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
# Cada app distinta debe tener su propio group.id para fan-out (todas ven TODOS los mensajes)
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "alert-module-v1")
KAFKA_TOPIC_IN = os.getenv("KAFKA_TOPIC_IN", "tshark_traces")
KAFKA_TOPIC_OUT = os.getenv("KAFKA_TOPIC_OUT", "snort_alerts")


# === SNORT CONFIG ===
SNORT_BASE_CMD = [
    "snort",
    "-c", SNORT_LUA,
    "-R", SNORT_RULES,
    "-A", ALERT_FILE,
    "--lua",
    f"{ALERT_FILE} = {{file = true, fields = 'msg timestamp pkt_num proto pkt_gen pkt_len dir src_ap dst_ap rule action'}}",
    "-l", ALERT_DIR
 ]
def run_snort_on_pcap(pcap_path, producer):
    """Ejecuta Snort3 en un hilo separado sobre un PCAP rotado."""
    alert_path = os.path.join(ALERT_DIR,f"{ALERT_FILE}.txt")

    if os.path.exists(alert_path): #FIXME BORRAR LUEGO
        print(f"PESO DEL FICHERO DE ALERTAS {os.path.getsize(alert_path)//8192} kB")

    if os.path.exists(alert_path) and os.path.getsize(alert_path) >= ALERT_ROTATE_SIZE_MB:
        try:
            os.remove(alert_path)
            print(f"✅ Fichero de alertas rotado con exito: {alert_path}")
        except Exception as e:
            print(f"❌ Error al borrar el fichero de alertas: {e}")

    cmd = SNORT_BASE_CMD + ["-r", pcap_path]
    print(f"⚡ Lanzando Snort3 sobre {pcap_path}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    def log_output(stream, prefix):
        for line in stream:
            print(f"[{prefix}] {line.strip()}")

    #threading.Thread(target=log_output, args=(proc.stdout, f"snort-out-{os.path.basename(pcap_path)}"), daemon=True).start()
    #threading.Thread(target=log_output, args=(proc.stderr, f"snort-err-{os.path.basename(pcap_path)}"), daemon=True).start()

    proc.wait()
    print(f"✅ Snort3 terminó con {pcap_path}")
    os.chmod(alert_path,0o664) #Necesita los permisos en octal, por eso el 0o

    #Leer alert_parth y mandarlo directamente a kafka con el producer. Controlar que solo se publiquen la nueva información
    if os.path.exists(alert_path):
        with open(alert_path, "r") as data:
            lines = data.readlines() #con esto leería todas las alertas todo el rato
        if not lines:
            print(f"⚠️ Fichero {alert_path} vacío")

        if data:
            producer.produce_lines(lines)

        
class Json2PcapWorker:
    """Proceso json2pcap que convierte JSON → PCAP"""

    def __init__(self, trace_path, j2p_path):
        self.trace_path = trace_path
        self.j2p_path = j2p_path
        self.proc = None
        self.first_packet = True
        self._start_proc()

    def _start_proc(self):
        cmd = [sys.executable, self.j2p_path, "-i", "-o", self.trace_path]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        # Abrimos el array JSON
        self.proc.stdin.write("[")
        self.proc.stdin.flush()
        threading.Thread(target=self._log_stderr, daemon=True).start()

    def _log_stderr(self):
        for line in self.proc.stderr:
            print(f"[json2pcap] {line.strip()}")

    def write_packet(self, packet_dict):
        try:
            if not self.first_packet:
                self.proc.stdin.write(",")
            else:
                self.first_packet = False
            json.dump(packet_dict, self.proc.stdin, ensure_ascii=False)
            self.proc.stdin.flush()
        except Exception as e:
            print(f"❌ Error escribiendo en json2pcap: {e}")

    def close(self):
        try:
            # Cerrar el array JSON
            self.proc.stdin.write("]")
            self.proc.stdin.flush()
            self.proc.stdin.close()
        except Exception as e:
            print(f"❌ Error cerrando stdin: {e}")
        self.proc.wait()


class PacketWriter:
    """Gestiona la rotación de ficheros y lanza Snort en cada rotación."""

    def __init__(self, output_dir, j2p_path, rotate_size_mb,producer):
        self.output_dir = output_dir
        self.j2p_path = j2p_path
        self.rotate_size = rotate_size_mb
        self.file_index = 0
        self.worker = None
        self.producer = producer
        #os.makedirs(output_dir, exist_ok=True)
        self._new_file()

    def _new_file(self):
        if self.worker:
            old_trace = self.worker.trace_path
            threading.Thread(target=self.worker.close, daemon=True).start()
            threading.Thread(target=self.run_snort_delete_file, args=(old_trace,self.producer,), daemon=True).start()

        trace_path = os.path.join(self.output_dir, f"trace_{self.file_index:02d}.pcapng")
        print(f"📂 Nuevo fichero abierto: {trace_path}")
        self.worker = Json2PcapWorker(trace_path, self.j2p_path)
        if self.file_index < 5:
            self.file_index += 1
        else:
            self.file_index = 0


    def write_packet(self, packet_dict):
        self.worker.write_packet(packet_dict)
        trace_file = self.worker.trace_path
        if os.path.exists(trace_file) and os.path.getsize(trace_file) >= self.rotate_size:
            self._new_file()

    def close(self):
        if self.worker:
            old_trace = self.worker.trace_path
            self.worker.close()
            threading.Thread(target=self.run_snort_delete_file, args=(old_trace,self.producer), daemon=True).start()

    def run_snort_delete_file(self,old_trace,producer):
        run_snort_on_pcap(old_trace,producer)
        try:
            os.remove(old_trace)
            print(f"✅ Fichero {old_trace} borrado con exito")
        except Exception as e:
            print(f"❌ Error borrando {old_trace}: {e}")

def main():
    producer = KafkaProducer(
        topic=KAFKA_TOPIC_OUT,
        bootstrap=KAFKA_BOOTSTRAP
    )
    writer = PacketWriter(OUTPUT_DIR, J2P_PATH, PCAP_ROTATE_SIZE_MB, producer)
    
    consumer = KafkaLineConsumer(
        topic=KAFKA_TOPIC_IN,
        message_field="message",
        group_id=KAFKA_GROUP_ID,       # <-- fan-out: este módulo con su propio group
        bootstrap=KAFKA_BOOTSTRAP
    )
    '''
    # Comando tshark
    tshark_command = [
        "tshark",
        "-T", "json",
        "-l",               # line-buffered
        "-x",
        "--no-duplicate-keys",
        "-i", TSHARK_INTERFACE
    ]

    print(f"🚀 Lanzando tshark: {' '.join(tshark_command)}")
'''


    open_braces = 0
    buffer = []


    for line in consumer.iter_lines():
        if "{" in line:
            open_braces += line.count("{")
        if open_braces > 0:
            buffer.append(line)
        if "}" in line:
            open_braces -= line.count("}")
            if open_braces == 0 and buffer:
                packet_str = "".join(buffer).rstrip()
                if packet_str.endswith(","):
                    packet_str = packet_str[:-1]
                try:
                    packet_dict = json.loads(packet_str)
                    writer.write_packet(packet_dict)
                except json.JSONDecodeError as e:
                    print(f"❌ Error parseando paquete: {e}")
                buffer = []

    writer.close()


if __name__ == "__main__":
    main()
