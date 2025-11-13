import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from kafka_io import KafkaLineConsumer, KafkaAlertProducer, get_bootstrap
from pymongo import MongoClient, errors
from scapy.all import Ether, sendp

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


# ================== UTILIDADES FICHEROS ==================

def ensure_mode_644(path: str):
    """
    Pone permisos 0644 solo si hace falta.
    """
    try:
        st_mode = os.stat(path).st_mode & 0o777
        if st_mode != 0o644:
            os.chmod(path, 0o644)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"⚠️  Could not ensure 0644 on {path}: {e}")


def truncate_alert_file(alert_path: str):
    """
    Deja el fichero de alertas vacío (para no re-procesar alertas viejas al arrancar).
    """
    try:
        os.makedirs(os.path.dirname(alert_path), exist_ok=True)
        with open(alert_path, "w"):
            pass
        print(f"🧹 Truncated {alert_path}")
    except Exception as e:
        print(f"⚠️ Could not truncate {alert_path}: {e}")


def insert_alert_line(alerts_collection, line: str):
    """
    Inserta UNA alerta (línea JSON) en MongoDB.
    Respeta el índice único (saltará DuplicateKeyError si ya existe).
    """
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

def create_tap_interface(ifname: str):
    """
    Crea una interfaz TAP dentro del contenedor (requiere --cap-add=NET_ADMIN).
    Si ya existe, simplemente la levanta.
    """
    try:
        # ¿ya existe?
        res = subprocess.run(["ip", "link", "show", ifname],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        if res.returncode != 0:
            print(f"🔧 Creating TAP interface {ifname}...")
            subprocess.run(["ip", "tuntap", "add", "dev", ifname, "mode", "tap"],
                           check=True)
        # Levantar interfaz
        subprocess.run(["ip", "link", "set", ifname, "up"], check=True)
        print(f"✅ TAP interface {ifname} is up")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error creating/bringing up TAP interface {ifname}: {e}")
        sys.exit(1)


def start_snort_live(ifname: str):
    """
    Lanza Snort3 en modo live ('-i ifname'), escribiendo alertas al fichero JSON.
    """
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

    # Si quieres ver logs de Snort, descomenta estas líneas:
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

from scapy.all import sendp, Packet as ScapyPacket  # import aquí para no romper si falta scapy en otros contextos


def extract_frame_bytes(packet_dict) -> bytes:
    """
    Extrae los bytes de la trama Ethernet a partir del dict JSON de tshark.
    Asume formato: {"_source": {"layers": { "frame_raw": [hex, pos, len, bitmask, type], ... } } }
    """
    try:
        layers = packet_dict["_source"]["layers"]
    except Exception as e:
        print(f"⚠️ Packet without '_source.layers': {e}")
        return None

    frame_raw = layers.get("frame_raw")
    if frame_raw is None:
        print("⚠️ No 'frame_raw' field found in packet")
        return None

    try:
        # En tshark típico: frame_raw = [hex_str, pos, len, bitmask, type]
        if isinstance(frame_raw, list) and len(frame_raw) > 0:
            hex_str = frame_raw[0]
        elif isinstance(frame_raw, str):
            hex_str = frame_raw
        else:
            print(f"⚠️ Unexpected frame_raw format: {type(frame_raw)}")
            return None

        return bytes(bytearray.fromhex(hex_str))
    except Exception as e:
        print(f"⚠️ Error converting frame_raw to bytes: {e}")
        return None


def inject_packet_to_tap(packet_dict, iface: str):
    frame_bytes = extract_frame_bytes(packet_dict)
    if not frame_bytes:
        return

    try:
        # Caso 1: ¿parece un frame Ethernet (tiene MAC dest + MAC src + EtherType)?
        if len(frame_bytes) >= 14:
            ethertype = int.from_bytes(frame_bytes[12:14], "big")

            # Rangos válidos de EtherType (0x0600+ son EtherTypes reales)
            if ethertype >= 0x0600:
                # Ya es Ethernet → enviar tal cual
                sendp(frame_bytes, iface=iface, verbose=False)
                return

        # Caso 2: no es Ethernet → creamos una cabecera dummy
        # Deducción del tipo (IPv4 vs IPv6)
        if frame_bytes[0] >> 4 == 4:      # IPv4
            ether = Ether(type=0x0800)
        elif frame_bytes[0] >> 4 == 6:    # IPv6
            ether = Ether(type=0x86DD)
        else:
            ether = Ether(type=0x0800)    # fallback

        pkt = ether / frame_bytes
        sendp(bytes(pkt), iface=iface, verbose=False)

    except Exception as e:
        print(f"❌ Error injecting packet into {iface}: {e}")


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
    create_tap_interface(TAP_IFACE)

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

    print("📥 Starting Kafka consume loop (network traces) -> TAP interface...")
    for msg, line in consumer.iter_records():
        if not line:
            consumer.commit_msg(msg)
            continue

        line = line.strip()
        try:
            print("RAW Kafka message:", line)
            packet_dict = json.loads(line)
        except json.JSONDecodeError:
            # Línea corrupta -> commit y seguir
            consumer.commit_msg(msg)
            continue

        # Inyectar directamente en la interfaz TAP (streaming real)
        inject_packet_to_tap(packet_dict, TAP_IFACE)

        # Confirmamos procesamiento del mensaje de Kafka
        consumer.commit_msg(msg)

    # Si salimos del bucle, cerramos Snort
    try:
        snort_proc.terminate()
    except Exception:
        pass


if __name__ == "__main__":
    main()