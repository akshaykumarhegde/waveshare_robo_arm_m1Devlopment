import serial
import json
import time

PORT = '/dev/ttyUSB0' 
BAUD = 115200

try:
    ser = serial.Serial(PORT, BAUD, timeout=1)
    print(f"Connected to RoArm-M1 on {PORT}")
    time.sleep(2)  # Wait for the board to initialize

    # T: 101 commands raw radians to the arm joints
    cmd = {
        "T": 101, 
        "base": 0.0, 
        "shoulder": 0.0, 
        "elbow": 0.0, 
        "hand": 0.0
    }

    json_cmd = json.dumps(cmd) + "\n"
    ser.write(json_cmd.encode('utf-8'))
    print(f"Sent command: {json_cmd.strip()}")

    ser.close()
except Exception as e:
    print(f"Error communicating with arm: {e}")
