import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import fcntl
import struct

from kafka_io import KafkaLineConsumer, KafkaAlertProducer, get_bootstrap
from pymongo import MongoClient, errors

# ====== RUTAS / CONFIG FICHEROS ======
PFD = Path(__file__).resolve().parent  # /home/Alert_Module en el contenedor

SNORT_CONFIG_DIR = PFD / "Snort_configuration"
SNORT_LUA = str(SNORT_CONFIG_DIR / "lua" / "snort.lua")
SNORT_RULES = str(SNORT_CONFIG_DIR / "Rules" / "alert_rules.rules")
ALERT_DIR = str(PFD / "Alerts")
ALERT_FILE = "alert_json"
ALERT_PATH = os.path.join(ALERT_DIR, f"{ALERT_FILE}.txt")

# ====== KAFKA CONFIG ======
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "alert-module-v1")
KAFKA_TOPIC_IN = os.getenv("KAFKA_TOPIC_IN", "tshark_traces")
KAFKA_TOPIC_OUT = os.getenv("KAFKA_TOPIC_OUT", "snort_alerts")

# ====== TAP / INTERFAZ SNORT ======
TAP_IFACE = os.getenv("ALERT_TAP_IFACE", "tap0")

# ====== SNORT BASE CMD (sin -i/-r aún) ======
SNORT_BASE_CMD = [
    "snort",
    "-c", SNORT_LUA,
    "-R", SNORT_RULES,
    "-A", ALERT_FILE,
    "--lua",
    f"{ALERT_FILE} = {{file = true, fields = 'msg timestamp pkt_num proto pkt_gen pkt_len dir src_ap dst_ap rule action'}}",
    "-l", ALERT_DIR,
    "-k", "none",
]

# ====== CONSTANTES TUN/TAP ======
TUNSETIFF = 0x400454ca
IFF_TAP = 0x0002
IFF_NO_PI = 0x1000

# ================== UTILIDADES FICHEROS ==================

def ensure_mode_644(path: str):
    """Pone permisos 0644 solo si hace falta."""
    try:
        st_mode = os.stat(path).st_mode & 0o777
        if st_mode != 0o644:
            os.chmod(path, 0o644)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"⚠️  Could not ensure 0644 on {path}: {e}")


def truncate_alert_file(alert_path: str):
    """Deja el fichero de alertas vacío (para no re-procesar alertas viejas al arrancar)."""
    try:
        os.makedirs(os.path.dirname(alert_path), exist_ok=True)
        with open(alert_path, "w"):
            pass
        print(f"🧹 Truncated {alert_path}")
    except Exception as e:
        print(f"⚠️ Could not truncate {alert_path}: {e}")


def insert_alert_line(alerts_collection, line: str):
    """Inserta UNA alerta (línea JSON) en MongoDB."""
    try:
        alert_doc = json.loads(line)
    except json.JSONDecodeError:
        print(f"⚠️ Error decoding JSON alert line: {line}")
        return

    try:
        alerts_collection.insert_one(alert_doc)
    except errors.DuplicateKeyError:
        # ya existe, sin drama
        pass
    except errors.ServerSelectionTimeoutError:
        print("❌ MongoDB connection timeout while inserting alert. Will continue...")
    except Exception as e:
        print(f"❌ Error inserting alert: {e}")


# ================== TAP & SNORT LIVE ==================

def open_tap_interface(ifname: str) -> int:
    """
    Abre (y si hace falta crea) una interfaz TAP usando /dev/net/tun y devuelve su descriptor.
    Requiere:
      - dispositivo /dev/net/tun montado en el contenedor
      - capabilities NET_ADMIN (ya las tienes en docker-compose)
    """
    try:
        tun_fd = os.open("/dev/net/tun", os.O_RDWR)
    except OSError as e:
        print(f"❌ Cannot open /dev/net/tun: {e}")
        sys.exit(1)

    ifr = struct.pack("16sH", ifname.encode(), IFF_TAP | IFF_NO_PI)
    try:
        fcntl.ioctl(tun_fd, TUNSETIFF, ifr)
    except OSError as e:
        print(f"❌ TUNSETIFF failed for {ifname}: {e}")
        os.close(tun_fd)
        sys.exit(1)

    # Levantar interfaz en modo UP
    try:
        subprocess.run(["ip", "link", "set", ifname, "up"], check=True)
        print(f"✅ TAP interface {ifname} is up (fd={tun_fd})")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Could not bring {ifname} up: {e}")

    return tun_fd


def start_snort_live(ifname: str):
    """Lanza Snort3 en modo live ('-i ifname'), escribiendo alertas al fichero JSON."""
    cmd = SNORT_BASE_CMD + ["-i", ifname]
    print(f"🚀 Starting Snort3 live on interface {ifname}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    def _log_stream(stream, prefix):
        for line in stream:
            print(f"[{prefix}] {line.strip()}")

    threading.Thread(target=_log_stream, args=(proc.stdout, "snort-out"), daemon=True).start()
    threading.Thread(target=_log_stream, args=(proc.stderr, "snort-err"), daemon=True).start()

    return proc


# ================== TAIL DE ALERTAS SNORT ==================

def alerts_tail_loop(alert_path: str, producer: KafkaAlertProducer, alerts_collection):
    """
    Lee continuamente nuevas líneas del fichero de alertas de Snort y:
      - las envía a Kafka
      - las inserta en MongoDB
    """
    # Asegurar que el fichero existe
    os.makedirs(os.path.dirname(alert_path), exist_ok=True)
    if not os.path.exists(alert_path):
        open(alert_path, "a").close()
    ensure_mode_644(alert_path)

    print(f"📡 Starting alerts tail on {alert_path}")
    with open(alert_path, "r", encoding="utf-8", errors="replace") as f:
        # Ir al final del fichero (solo procesar líneas nuevas)
        f.seek(0, os.SEEK_END)

        buffer = []
        last_flush = time.time()
        FLUSH_INTERVAL = 1.0  # segs

        while True:
            line = f.readline()
            if not line:
                # Sin datos nuevos -> pequeña espera
                time.sleep(0.5)
            else:
                line = line.strip()
                if not line:
                    continue

                # 1) Enviar a Kafka (lote para eficiencia)
                buffer.append(line)
                if time.time() - last_flush >= FLUSH_INTERVAL:
                    try:
                        producer.produce_lines(buffer)
                    except Exception as e:
                        print(f"❌ Error publishing alerts to Kafka: {e}")
                    buffer.clear()
                    last_flush = time.time()

                # 2) Insertar en MongoDB
                if alerts_collection is not None:
                    insert_alert_line(alerts_collection, line)


# ================== EXTRACCIÓN Y ENVÍO DE TRÁFICO A TAP ==================

def extract_frame_bytes(packet_dict) -> bytes:
    """
    Extrae los bytes de la trama Ethernet completa a partir del dict JSON de tshark.
    Usamos preferentemente 'frame_raw', que ya contiene:
        dst_mac | src_mac | ethertype | payload...
    """
    try:
        layers = packet_dict["_source"]["layers"]
    except Exception:
        print("⚠️ Missing _source.layers in packet")
        return None

    frame_raw = layers.get("frame_raw")
    if frame_raw is None:
        # Hay paquetes que solo traen eth_raw/ip_raw/...; de momento los ignoramos
        print("⚠️ No 'frame_raw' in packet, skipping injection for this packet")
        return None

    try:
        if isinstance(frame_raw, list) and len(frame_raw) > 0:
            hex_str = frame_raw[0]
        elif isinstance(frame_raw, str):
            hex_str = frame_raw
        else:
            print(f"⚠️ Unexpected frame_raw format: {frame_raw}")
            return None

        return bytes.fromhex(hex_str)
    except Exception as e:
        print(f"⚠️ Error converting frame_raw to bytes: {e}")
        return None


def inject_packet_to_tap(packet_dict, tap_fd: int):
    """
    Inyecta el paquete en el descriptor TAP (nivel 2) escribiendo directamente en /dev/net/tun.
    Aquí ya NO usamos sockets RAW ni Scapy → evitamos [Errno 90] Message too long.
    """
    frame_bytes = extract_frame_bytes(packet_dict)
    if not frame_bytes:
        return

    try:
        os.write(tap_fd, frame_bytes)
    except OSError as e:
        print(f"❌ Error writing frame to TAP fd={tap_fd}: {e}")


# ================== MAIN ==================

def main():
    # ---- MongoDB ----
    mongo_uri = os.getenv("MONGO_URI", "mongodb://admin:admin123@mongodb:27017/")
    try:
        client = MongoClient(mongo_uri)
        db = client["snort_db"]
        alerts_collection = db["alerts"]

        existing_indexes = alerts_collection.index_information()
        if "timestamp_1" not in existing_indexes:
            try:
                alerts_collection.create_index(
                    [("timestamp", 1), ("msg", 1), ("src_ap", 1)],
                    unique=True
                )
                print("✅ Unique index created on fields 'timestamp, msg, src_ap'")
            except errors.OperationFailure as e:
                print(f"⚠️ Could not create unique index: {e}")
        else:
            print("ℹ️ Unique index already exists on ('timestamp','msg','src_ap').")
    except Exception as e:
        print(f"❌ Error connecting to MongoDB: {e}")
        alerts_collection = None

    # ---- Kafka producer (alertas) ----
    kafka_producer = KafkaAlertProducer(
        topic=KAFKA_TOPIC_OUT,
        bootstrap=get_bootstrap()
    )

    # ---- TAP + Snort live ----
    tap_fd = open_tap_interface(TAP_IFACE)

    # Limpiar fichero de alertas antes de empezar (no procesar alertas antiguas)
    truncate_alert_file(ALERT_PATH)

    snort_proc = start_snort_live(TAP_IFACE)

    # Hilo para leer alertas de Snort en tiempo real
    threading.Thread(
        target=alerts_tail_loop,
        args=(ALERT_PATH, kafka_producer, alerts_collection),
        daemon=True
    ).start()

    # ---- Kafka consumer (tráfico de red) ----
    consumer = KafkaLineConsumer(
        topic=KAFKA_TOPIC_IN,
        message_field="_source",
        group_id=KAFKA_GROUP_ID,
        bootstrap=get_bootstrap()
    )

    print("📥 Starting Kafka consume loop (network traces) -> TAP interface.")
    for msg, line in consumer.iter_records():
        if not line:
            consumer.commit_msg(msg)
            continue

        line = line.strip()
        try:
            #print("ℹ️ RAW Kafka message:", line) # Usar solo para ver el paquete raw
            packet_dict = json.loads(line)
        except json.JSONDecodeError:
            # Línea corrupta -> commit y seguir
            consumer.commit_msg(msg)
            continue

        # Inyectar directamente en la interfaz TAP (streaming real)
        inject_packet_to_tap(packet_dict, tap_fd)

        # Confirmamos procesamiento del mensaje de Kafka
        consumer.commit_msg(msg)

    # Si salimos del bucle, cerramos Snort
    try:
        snort_proc.terminate()
    except Exception:
        pass

    try:
        os.close(tap_fd)
    except Exception:
        pass


if __name__ == "__main__":
    main()
