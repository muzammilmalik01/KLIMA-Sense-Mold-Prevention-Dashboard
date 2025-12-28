import serial
import json
import sqlite3
import datetime
import time
import sys
import re

# --- CONFIGURATION ---
# macOS: "/dev/cu.usbmodem..." 
# Linux: "/dev/ttyACM0"
SERIAL_PORT = "/dev/ttyACM0"  
BAUD_RATE = 115200
DB_NAME = "sensor_network.db"

# --- DATABASE MANAGEMENT ---

def init_db():
    """Creates the necessary tables if they don't exist."""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Enable Write-Ahead Logging (WAL) to prevent "Database Locked" errors
        c.execute("PRAGMA journal_mode=WAL;")

        # 1. Readings Table (Environment Data + VTT)
        c.execute('''CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            node_ip TEXT,
            room_name TEXT,
            temperature REAL,
            humidity REAL,
            mold_index REAL,
            risk_level INTEGER,
            is_simulated INTEGER DEFAULT 0
        )''')

        # 2. Device Health Table (Hardware Status)
        c.execute('''CREATE TABLE IF NOT EXISTS device_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            node_ip TEXT,
            room_name TEXT,
            sensor_a_status INTEGER,
            sensor_b_status INTEGER
        )''')

        # 3. System Alerts Table (Network Events & Critical Errors)
        c.execute('''CREATE TABLE IF NOT EXISTS system_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
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

def save_to_db(ip, payload):
    """Sorts the JSON payload into the correct table."""
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        c = conn.cursor()
        
        room = payload.get("room_name", "Unknown")

        # --- CASE A: System Alerts (e.g., Node Lost) ---
        if payload.get("event") == "node_lost":
            c.execute("INSERT INTO system_alerts (node_ip, room_name, event_type, message) VALUES (?, ?, ?, ?)",
                      (ip, room, "NODE_LOST", "Heartbeat timeout"))
            print(f"🚨 ALERT Saved: {ip} Lost")

        # --- CASE B: Device Health (Sensor Status) ---
        elif "sensor_1_status" in payload:
            s1 = payload.get("sensor_1_status")
            s2 = payload.get("sensor_2_status")
            
            # Save to Health Table
            c.execute("INSERT INTO device_health (node_ip, room_name, sensor_a_status, sensor_b_status) VALUES (?, ?, ?, ?)",
                      (ip, room, s1, s2))
            
            # If Critical Failure, ALSO save to Alerts Table
            if s1 > 1 or s2 > 1:
                msg = f"Critical Sensor Fail: A={s1}, B={s2}"
                c.execute("INSERT INTO system_alerts (node_ip, room_name, event_type, message) VALUES (?, ?, ?, ?)",
                          (ip, room, "SENSOR_FAIL", msg))
                print(f"⚠️  Hardware Failure Logged: {room}")
            else:
                print(f"🔧 Health Logged: {room}")

        # --- CASE C: Sensor Readings (Data & VTT) ---
        # Note: Checking "temparature" (your C code spelling)
        elif "temparature" in payload:
            temp = payload.get("temparature")
            hum = payload.get("humidity")
            mold = payload.get("mold_index") # Can be None
            risk = payload.get("mold_risk_status") # Can be None
            
            # Extract Simulation Flag (Default to 0 if missing)
            is_sim = payload.get("sim", 0)

            c.execute('''INSERT INTO readings 
                         (node_ip, room_name, temperature, humidity, mold_index, risk_level, is_simulated) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (ip, room, temp, hum, mold, risk, is_sim))
            
            # Console Feedback
            sim_tag = "[SIM]" if is_sim else ""
            if mold is not None:
                print(f"📊 {sim_tag} VTT Data: {room} | T:{temp}°C H:{hum}% | Mold:{mold}")
            else:
                print(f"📉 {sim_tag} Telemetry: {room} | T:{temp}°C H:{hum}%")

        conn.commit()
        conn.close()

    except sqlite3.Error as e:
        print(f"❌ SQL Error: {e}")

# --- MAIN SERIAL LOOP ---

def main():
    # 1. Setup DB
    init_db()
    
    # 2. Regex to strip ANSI color codes (from Zephyr shell)
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    try:
        # 3. Open Serial
        ser = serial.Serial(
            SERIAL_PORT, 
            BAUD_RATE, 
            timeout=1,
            xonxoff=False, 
            rtscts=False, 
            dsrdtr=False
        )
        # DTR/RTS Dance for MacOS/Zephyr stability
        ser.dtr = True 
        ser.rts = True
        ser.reset_input_buffer()

        print(f"--- 🔌 Connected to {SERIAL_PORT} ---")
        print("--- 💾 Logging to SQLite. Press Ctrl+C to stop ---")

        while True:
            try:
                # Read line
                line_bytes = ser.read_until(b'\n')
                if not line_bytes: continue

                # Decode & Clean
                line = line_bytes.decode('utf-8', errors='replace').strip()
                line = ansi_escape.sub('', line) # Remove colors
                
                # Ignore shell prompts
                if "uart:~$" in line: continue

                # --- PARSING LOGIC ---
                if line.startswith("[DATA]:"):
                    # Remove the tag
                    content = line.replace("[DATA]:", "").strip()
                    
                    # Default values
                    node_ip = "Unknown"
                    json_str = content

                    # SPLIT LOGIC: Look for the pipe "|"
                    # Format: "fdde::1 | {json}"
                    if "|" in content:
                        parts = content.split("|", 1)
                        if len(parts) == 2:
                            node_ip = parts[0].strip()
                            json_str = parts[1].strip()
                    
                    # Parse JSON
                    try:
                        payload = json.loads(json_str)
                        # Save to DB
                        save_to_db(node_ip, payload)
                    except json.JSONDecodeError:
                        print(f"⚠️  JSON Parse Error: {json_str}")

                elif line.startswith("[ALERT]:"):
                     print(f"🚨 SYSTEM ALERT: {line}")

            except OSError:
                print("❌ Serial Connection Lost! Retrying...")
                time.sleep(1)

    except serial.SerialException as e:
        print(f"❌ Could not open port {SERIAL_PORT}: {e}")
    except KeyboardInterrupt:
        print("\n👋 Saving & Exiting...")
        if 'ser' in locals() and ser.is_open:
            ser.close()
        sys.exit(0)

if __name__ == "__main__":
    main()