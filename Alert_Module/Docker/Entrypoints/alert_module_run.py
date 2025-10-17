import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from kafka_io import KafkaLineConsumer, KafkaAlertProducer, get_bootstrap
from queue import Queue, Empty, Full

# === FILE CONFIG ===
PFD = Path(__file__).resolve().parent #/home/Alert_Module in container

OUTPUT_DIR = str(PFD / "Parsing" / "PCAP_Files")
J2P_PATH = str(PFD / "Parsing" / "JSON2PCAP" /"json2pcap.py")

SNORT_CONFIG_DIR = PFD / "Snort_configuration"
SNORT_LUA = str(SNORT_CONFIG_DIR / "lua" / "snort.lua")
SNORT_RULES = str(SNORT_CONFIG_DIR / "Rules" / "alert_rules.rules")
ALERT_DIR = str(PFD / "Alerts")
ALERT_FILE = "alert_json"

# === KAFKA CONFIG ===
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "flow-module-v1")
KAFKA_TOPIC_IN = os.getenv("KAFKA_TOPIC_IN", "tshark_traces")
KAFKA_TOPIC_OUT = os.getenv("KAFKA_TOPIC_OUT", "snort_alerts")

# === ROTATION ===
PCAP_ROTATE_SIZE_MB = 2 * 1024 * 1024       # ↑ 200 MB (menos rotaciones bajo ráfagas)
ALERT_ROTATE_SIZE_MB = 200 * 1024 #* 1024 200KB


# === WRITER CONTROL ===
PACKET_QUEUE_MAX = 100000                 # margen para ráfagas
WRITER_FLUSH_EVERY = 100                 # flush cada N
WATCHDOG_STALL_SECS = 120                # watchdog de inactividad


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
        cmd = ["python3", self.j2p_path, "-i", "-o", self.trace_path]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,   # evita bloquear por stdout
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
        """Escribe un objeto en el array JSON (sin flush por paquete)."""
        try:
            if not self.first_packet:
                self.proc.stdin.write(",")
            else:
                self.first_packet = False
            json.dump(packet_dict, self.proc.stdin, ensure_ascii=False)
            # NO flush aquí: se hace por lotes en el writer
        except Exception as e:
            print(f"❌ Error escribiendo en json2pcap: {e}")

    def close(self):
        try:
            self.proc.stdin.write("]")
            self.proc.stdin.flush()
            self.proc.stdin.close()
        except Exception as e:
            print(f"❌ Error cerrando stdin: {e}")
        self.proc.wait()


class PacketWriter:
    """Gestiona la rotación de ficheros y lanza CICFlowMeter en cada rotación (con cola y backoff)."""
    def __init__(self, output_dir, j2p_path, rotate_size_mb, producer):
        self.output_dir = output_dir
        self.j2p_path = j2p_path
        self.rotate_size = rotate_size_mb
        self.file_index = 0
        self.j2p_worker = None
        self.producer = producer
        os.makedirs(output_dir, exist_ok=True)

        self.q = Queue(maxsize=PACKET_QUEUE_MAX)
        self._last_write_ts = time.time()
        self._written_since_flush = 0
        self._running = True
        threading.Thread(target=self._writer_loop, daemon=True).start()

        self._new_file()

    def enqueue_packet(self, packet_dict, ack_fn=None):
        """Encola con reintentos cortos para no bloquear el hilo de consumo."""
        while self._running:
            try:
                self.q.put((packet_dict, ack_fn), timeout=0.1)
                return
            except Full:
                # backoff corto; el writer drenará la cola
                pass

    def _writer_loop(self):
        """Hilo que escribe paquetes al json2pcap y rota si toca."""
        while self._running:
            try:
                packet_dict, ack_fn = self.q.get(timeout=1)
            except Empty:
                if time.time() - self._last_write_ts > WATCHDOG_STALL_SECS:
                    print("⏱️  Watchdog: sin escritura reciente al PCAP", flush=True)
                continue

            try:
                self.j2p_worker.write_packet(packet_dict)
                self._written_since_flush += 1
                if self._written_since_flush >= WRITER_FLUSH_EVERY:
                    try:
                        self.j2p_worker.proc.stdin.flush()
                    except Exception:
                        pass
                    self._written_since_flush = 0

                trace_file = self.j2p_worker.trace_path
                if os.path.exists(trace_file) and os.path.getsize(trace_file) >= self.rotate_size:
                    self._new_file()

                self._last_write_ts = time.time()

                if ack_fn:
                    try:
                        ack_fn()
                    except Exception as e:
                        print(f"⚠️  Error en ack_fn: {e}", flush=True)
            except Exception as e:
                print(f"❌ Error en writer_loop: {e}", flush=True)

    def _new_file(self):
        if self.j2p_worker:
            old_trace = self.j2p_worker.trace_path
            threading.Thread(target=self.j2p_worker.close, daemon=True).start()
            threading.Thread(target=self._run_snort_and_delete, args=(old_trace,), daemon=True).start()

        trace_path = os.path.join(self.output_dir, f"trace_{self.file_index:02d}.pcapng")
        print(f"📂 Nuevo fichero abierto: {trace_path}")
        self.j2p_worker = Json2PcapWorker(trace_path, self.j2p_path)

        if self.file_index < 5:
            self.file_index += 1
        else:
            self.file_index = 0

    def write_packet(self, packet_dict):
        self.j2p_worker.write_packet(packet_dict)
        trace_file = self.j2p_worker.trace_path
        if os.path.exists(trace_file) and os.path.getsize(trace_file) >= self.rotate_size:
            self._new_file()

    def close(self):
        if self.j2p_worker:
            old_trace = self.j2p_worker.trace_path
            self.j2p_worker.close()
            threading.Thread(target=self._run_snort_and_delete, args=(old_trace,), daemon=True).start()
            self._running = False

    def _run_snort_and_delete(self, old_trace):
        run_snort_on_pcap(old_trace, self.producer)
        try:
            os.remove(old_trace)
            print(f"✅ Fichero {old_trace} borrado con éxito")
        except Exception as e:
            print(f"❌ Error borrando {old_trace}: {e}")


def main():
    kafka_producer = KafkaAlertProducer(
        topic=KAFKA_TOPIC_OUT,
        bootstrap=get_bootstrap()
    )

    writer = PacketWriter(
        output_dir=OUTPUT_DIR,
        j2p_path=J2P_PATH,
        rotate_size_mb=PCAP_ROTATE_SIZE_MB,
        producer=kafka_producer
    )

    consumer = KafkaLineConsumer(
        topic=KAFKA_TOPIC_IN,
        message_field="_source",
        group_id=KAFKA_GROUP_ID,
        bootstrap=get_bootstrap()
    )

    for msg, line in consumer.iter_records():
        if not line:
            consumer.commit_msg(msg)
            continue
        line = line.strip()
        try:
            packet_dict = json.loads(line)
        except json.JSONDecodeError:
            # línea corrupta → sáltala
            consumer.commit_msg(msg)
            continue

        # Encolamos para json2pcap (tu writer actual)
        writer.enqueue_packet(
            packet_dict,
            ack_fn=lambda m=msg: consumer.commit_msg(m)
        )

    writer.close()


if __name__ == "__main__":
    main()

