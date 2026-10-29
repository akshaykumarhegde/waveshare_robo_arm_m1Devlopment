# Waveshare RoArm-M1 Demonstration & Control Suite

This directory contains a complete software suite to demo, test, and control the **Waveshare RoArm-M1** 5-DOF robotic arm.

---

## 📋 Available Demos

| Script / File | Description | Interface |
| :--- | :--- | :--- |
| **[`roarm_gui.py`](../roarm_gui.py)** | **All-in-one standalone Desktop GUI Studio** with live 2D vector kinematics, joint sliders, Cartesian IK, one-click demos, and telemetry | **Desktop GUI (Tkinter)** |
| **[`roarm_record_play_gui.py`](../roarm_record_play_gui.py)** | **Teach & Play Studio**: Hand-teaching mode, 1-click waypoint capture, live trajectory recording, sequence timeline editor, speed multiplier, and ESP32 flash sync | **Desktop GUI (Tkinter)** |
| **[`roarm_serial_console.py`](../roarm_serial_console.py)** | **Dedicated Serial Command Studio** with live bidirectional terminal, protocol builder, command presets, macro runner, and live joint telemetry | **Desktop GUI (Tkinter)** |
| **[`roarm_driver.py`](roarm_driver.py)** | Core Python driver implementing full JSON protocol (T:0 to T:13), auto-port detection, and simulation fallback | Python Library |
| **[`demo_motions.py`](demo_motions.py)** | Automated 6-step demo: Diagnostics, Homing, Greeting Wave, 3D Cartesian Pick-and-Place, Circular Scan, Park | CLI / Automated |
| **[`demo_interactive.py`](demo_interactive.py)** | Interactive terminal console for jogging individual joints, Cartesian jog, gripper, hand-teach & replay | Interactive CLI |
| **[`demo_wifi_http.py`](demo_wifi_http.py)** | Wireless Wi-Fi REST API client to control the arm over the ESP32 onboard HTTP server | Wi-Fi / HTTP |
| **[`demo_web_dashboard.html`](demo_web_dashboard.html)** | Modern Web dashboard with real-time SVG arm kinematics, sliders, and direct 1-click **WebSerial USB** connection | Browser (Chrome/Edge) |
| **[`ros2_demo_publisher.py`](ros2_demo_publisher.py)** | ROS 2 automated trajectory publisher driving `/joint_states` for RViz2 and `serial_ctrl` | ROS 2 Node |

---

## ⚡ Quick Start

### 1. Hardware Connection & Permissions
1. Connect the **12V 5A DC power supply** to the RoArm-M1 driver board.
2. Connect the arm to your PC via a **USB-C / USB cable**.
3. Grant serial access permissions on Linux:
   ```bash
   sudo chmod 777 /dev/ttyUSB* /dev/ttyACM*
   # or add your user to dialout:
   sudo usermod -a -G dialout $USER
   ```

### 2. Run the Automated Motion Demo
Run the automated showpiece sequence:
```bash
# Auto-detects port or runs in mock simulation mode if disconnected:
python3 demo_motions.py

# Or specify your port explicitly:
python3 demo_motions.py --port /dev/ttyUSB0

# Continuous looping exhibition mode:
python3 demo_motions.py --loop
```

### 3. Run the Interactive Control Console
For manual jogging, gripper testing, and teaching:
```bash
python3 demo_interactive.py
```

### 4. Open the Web Dashboard (No Installation Required!)
Simply open [`demo_web_dashboard.html`](demo_web_dashboard.html) in Google Chrome, Microsoft Edge, or Opera:
```bash
xdg-open demo_web_dashboard.html
# or open in browser: file:///path/to/demo_web_dashboard.html
```
- Click **"Connect USB (WebSerial)"** to control the physical arm directly from your browser.
- Enjoy live visual SVG kinematics, preset triggers (Wave, Pick & Place, Dance), and real-time JSON protocol logging!

### 5. Control over Wi-Fi
1. Turn on the RoArm-M1 and connect your PC or phone to its Wi-Fi hotspot:
   - **SSID:** `ESP32_DEV`
   - **Password:** `12345678`
2. Run the Wi-Fi controller:
   ```bash
   python3 demo_wifi_http.py --ip 192.168.4.1
   ```

### 6. ROS 2 Integration Demo
In separate terminal tabs:
```bash
# Terminal 1: Launch RViz2 and Robot State Publisher
ros2 launch roarm roarm.launch.py gui:=False

# Terminal 2: Start Serial Bridge Node to Physical Arm
ros2 run serial_ctrl serial_ctrl --ros-args -p serial_port:=/dev/ttyUSB0

# Terminal 3: Run Automated Trajectory Demo
python3 ros2_demo_publisher.py
```

---

## 📖 RoArm-M1 JSON Protocol Reference

| `T` (Type) | Name | Example JSON Payload | Description |
| :---: | :--- | :--- | :--- |
| `0` | **Emergency Stop** | `{"T": 0}` | Immediately halts motion and cuts motor torque |
| `1` | **Joint Angle Control** | `{"T":1,"P1":180,"P2":10,"P3":90,"P4":90,"P5":180,"S1":200,"S2":200,"S3":200,"S4":200,"S5":200,"A1":60,"A2":60,"A3":60,"A4":60,"A5":60}` | Moves joints 1–5 to specified degree angles |
| `11` | **Angle Init** | `{"T": 11}` | Returns joints to calibrated initial angle stance |
| `2` | **Cartesian IK Control**| `{"T":2,"P1":277.5,"P2":-13.8,"P3":276.6,"P4":90,"P5":180,"S1":10,"S5":200}` | Inverse kinematics: X, Y, Z (mm), Pitch Theta (°), Gripper (°) |
| `12` | **Coord Init** | `{"T": 12}` | Returns to initial Cartesian coordinates |
| `3` | **Raw ST Servo Pos** | `{"T":3,"P1":2047,"P2":0,"P3":3500,"P4":1500,"P5":2047,...}` | Raw servo encoder ticks (0-4095, center: 2047) |
| `4` | **Get Device Info** | `{"T": 4}` | Returns device name, MAC, and Wi-Fi mode |
| `5` | **Get Angles & Loads** | `{"T": 5}` | Returns real-time angle and load/torque for all 5 servos |
| `8` | **Record / Replay** | `{"T":8,"P1":0}` (Torque OFF) / `{"T":8,"P1":1}` (Torque ON)<br>`{"T":8,"P1":5,"P2":1,"P3":5}` (Save step 1)<br>`{"T":8,"P1":6,"P2":500,"P3":1}` (Replay) | Teach-and-play in ESP32 Flash memory |
| `10` | **Help** | `{"T": 10}` | Returns ASCII firmware instructions |
