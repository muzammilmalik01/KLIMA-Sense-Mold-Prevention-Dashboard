"""
KLIMA Sense Data Logger
=======================
Reads sensor data from the Thread network via USB serial and logs to SQLite.

Runs continuously on Raspberry Pi to populate sensor_network.db.
"""

import serial
import json
import sqlite3
import time
import sys
import re

# --- CONFIGURATION ---
# UPDATE THIS PORT to match your specific connection
# Mac Example:  /dev/cu.usbmodem0010502524601
# Raspberry Pi: /dev/ttyACM0 or /dev/ttyUSB0
SERIAL_PORT = "/dev/ttyACM0"  
BAUD_RATE = 115200
DB_NAME = "sensor_network.db"

# --- DATABASE MANAGEMENT ---

def init_db():
    """Creates the necessary tables if they don't exist."""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Enable Write-Ahead Logging (WAL) for concurrency
        c.execute("PRAGMA journal_mode=WAL;")

        # 1. Readings Table (Environment Data + VTT)
        c.execute('''CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT (datetime('now', 'localtime')),
            node_ip TEXT,
            room_name TEXT,
            temperature REAL,
            humidity REAL,
            mold_index REAL,
            risk_level INTEGER,
            growth_status INTEGER,
            rh_crit REAL,
            is_simulated INTEGER DEFAULT 0
        )''')

        # 2. Device Health Table (Hardware Status History)
        c.execute('''CREATE TABLE IF NOT EXISTS device_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT (datetime('now', 'localtime')),
            node_ip TEXT,
            room_name TEXT,
            sensor_a_status INTEGER,
            sensor_b_status INTEGER
        )''')

        # 3. System Alerts Table (Network Events & Critical Errors)
        c.execute('''CREATE TABLE IF NOT EXISTS system_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT (datetime('now', 'localtime')),
            node_ip TEXT,
            room_name TEXT,
            event_type TEXT,
            message TEXT
        )''')        
        conn.commit()
        conn.close()
        print(f"✅ Database initialized: {DB_NAME}")
    except Exception as e:
        print(f"❌ Database Init Failed: {e}")
        sys.exit(1)

def log_system_event(event_type, message):
    """Logs system-wide events (Server Status) to the alerts table."""
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        c = conn.cursor()
        # We use 'SERVER' as the node_ip for the Gateway itself
        c.execute("INSERT INTO system_alerts (node_ip, room_name, event_type, message) VALUES (?, ?, ?, ?)",
                  ("SERVER", "Gateway", event_type, message))
        conn.commit()
        conn.close()
        print(f"🚨 SYSTEM LOG: {event_type} - {message}")
    except Exception as e:
        print(f"❌ Failed to log system event: {e}")

def save_to_db(ip, payload):
    """Sorts the JSON payload into the correct table and translates codes."""
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        c = conn.cursor()
        
        # --- FIX: Check both 'room_name' (Telemetry) and 'room' (Alerts) ---
        room = payload.get("room_name") or payload.get("room") or "Unknown"

        # --- EXTRACT EVENT TYPE ---
        event = payload.get("event")

        # --- CASE A: System Alerts (Network & Sensor Failures) ---
        if event in ["node_lost", "node_reconnected", "node_joined", "sensor_fail", "sensor_fixed"]:
            
            # Map raw event strings to DB Enum types
            event_type_map = {
                "node_lost": "NODE_LOST",
                "node_reconnected": "NODE_RESTORED",
                "node_joined": "NODE_JOINED",
                "sensor_fail": "SENSOR_FAIL",
                "sensor_fixed": "SENSOR_FIXED"
            }
            
            # Map Hardware Status Codes to Human Readable Text
            health_code_map = {
                0: "Healthy",
                1: "Sensor Drift (>5%)",
                2: "Bus Error (SDA/SCL Wiring)",
                3: "Sensor Missing/Unplugged",
                4: "Power Failure (VCC/GND)",
                5: "Data Fetch Failed",
                6: "Internal Driver Error (Temp)",
                7: "Internal Driver Error (Humi)",
                8: "Internal Driver Error (Both)",
                9: "Temp Out of Range",
                10: "Humi Out of Range",
                11: "Garbage Data"
            }

            # Construct the Message
            message = ""
            
            if event == "sensor_fail":
                # Translate integer codes to text
                s1_code = payload.get("s1", 0)
                s2_code = payload.get("s2", 0)
                errors = []
                if s1_code > 1: errors.append(f"Sensor A: {health_code_map.get(s1_code, 'Unknown')}")
                if s2_code > 1: errors.append(f"Sensor B: {health_code_map.get(s2_code, 'Unknown')}")
                message = " | ".join(errors)
                
            elif event == "sensor_fixed":
                message = "Maintenance Complete. Sensors Operational."
            
            elif event == "node_lost":
                message = "Heartbeat timeout"
            elif event == "node_reconnected":
                message = "Connection re-established"
            elif event == "node_joined":
                message = "New device registered on network"
            
            # Save to DB
            c.execute("INSERT INTO system_alerts (node_ip, room_name, event_type, message) VALUES (?, ?, ?, ?)",
                      (ip, room, event_type_map[event], message))
            print(f"🚨 ALERT Saved: {event_type_map[event]} - {room}")

        # --- CASE B: Device Health (Continuous Logging) ---
        elif "sensor_1_status" in payload:
            s1 = payload.get("sensor_1_status")
            s2 = payload.get("sensor_2_status")
            c.execute("INSERT INTO device_health (node_ip, room_name, sensor_a_status, sensor_b_status) VALUES (?, ?, ?, ?)",
                      (ip, room, s1, s2))
            # Note: We do NOT create alerts here anymore to avoid spam. 
            # Alerts are handled by CASE A ("sensor_fail").
            print(f"🔧 Health Logged: {room}")

        # --- CASE C: Sensor Readings (Telemetry) ---
        elif "temparature" in payload:
            temp = payload.get("temparature")
            hum = payload.get("humidity")
            mold = payload.get("mold_index") 
            risk = payload.get("mold_risk_status") 
            growth = payload.get("growth_status")
            rh_crit = payload.get("rh_crit")
            is_sim = payload.get("sim", 0)

            c.execute('''INSERT INTO readings 
                         (node_ip, room_name, temperature, humidity, mold_index, risk_level, growth_status, rh_crit, is_simulated) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (ip, room, temp, hum, mold, risk, growth, rh_crit, is_sim))
            
            sim_tag = "[SIM]" if is_sim else ""
            if mold is not None:
                print(f"📊 {sim_tag} VTT Data: {room} | T:{temp}°C H:{hum}% | Mold:{mold}")
            else:
                print(f"📉 {sim_tag} Telemetry: {room} | T:{temp}°C H:{hum}%")

        conn.commit()
        conn.close()

    except sqlite3.Error as e:
        print(f"❌ SQL Error: {e}")
    except Exception as e:
        print(f"❌ Processing Error: {e}")

# --- MAIN LOOP ---

def main():
    init_db()
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    
    ser = None
    server_online = False 

    print(f"--- 🔌 Starting Logger on {SERIAL_PORT} ---")
    
    while True:
        try:
            # A. CONNECTION PHASE
            if ser is None or not ser.is_open:
                ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
                ser.dtr = True 
                ser.rts = True
                # ser.reset_input_buffer() # Disabled to ensure we see startup alerts
                
                if not server_online:
                    log_system_event("SERVER_RESTORED", "Connection to Gateway established.")
                    print("✅ Server Online!")
                    server_online = True

            # B. READING PHASE
            try:
                line_bytes = ser.read_until(b'\n')
            except serial.SerialException:
                raise OSError("Serial Disconnect")

            if not line_bytes: continue

            # Decode & Clean
            line = line_bytes.decode('utf-8', errors='replace').strip()
            line = ansi_escape.sub('', line) 
            
            # Clean Shell Prompts
            if "uart:~$" in line:
                line = line.replace("uart:~$", "").strip()

            # --- PARSING LOGIC ---
            # Using 'in' instead of 'startswith' to handle log noise
            if "[DATA]:" in line:
                try:
                    # Robust extraction: Grab everything after the first [DATA]:
                    relevant_part = line.split("[DATA]:", 1)[1].strip()
                    
                    # Split IP from JSON (Format: IP | JSON)
                    node_ip = "Unknown"
                    json_str = relevant_part

                    if "|" in relevant_part:
                        parts = relevant_part.split("|", 1)
                        if len(parts) == 2:
                            node_ip = parts[0].strip()
                            json_str = parts[1].strip()
                    
                    # Parse & Save
                    payload = json.loads(json_str)
                    save_to_db(node_ip, payload)
                
                except (IndexError, json.JSONDecodeError):
                    print(f"⚠️  Parse Error: {line}")

            elif "[ALERT]:" in line:
                 print(f"🚨 SYSTEM ALERT: {line}")

        except (OSError, serial.SerialException):
            if server_online:
                log_system_event("SERVER_LOST", "Gateway unreachable.")
                print("❌ Server Connection Lost! Retrying...")
                server_online = False
            
            if ser and ser.is_open: ser.close()
            ser = None
            time.sleep(2)

        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            if ser and ser.is_open: ser.close()
            sys.exit(0)

if __name__ == "__main__":
    main()