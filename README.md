# 🦾 Waveshare RoArm-M1 Robotic Arm Development Suite

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![ROS 2](https://img.shields.io/badge/ROS%202-Humble%20%7C%20Iron-orange.svg)](https://docs.ros.org/)
[![Hardware Verified](https://img.shields.io/badge/Hardware-RoArm--M1%20Verified-success.svg)](https://www.waveshare.com/wiki/RoArm-M1)
[![License](https://img.shields.io/badge/License-GPL%2FMIT-green.svg)](LICENSE)

An end-to-end, hardware-verified development suite and graphical control ecosystem for the **Waveshare RoArm-M1** 5-DOF robotic arm. Features standalone Desktop GUI Studios, a Hand-Teaching Waypoint Sequencer, a real-time Serial Command Studio, Python SDK drivers, an in-browser WebSerial dashboard, and a complete ROS 2 integration package.

---

## 📑 Table of Contents

- [Overview & Hardware Specs](#-overview--hardware-specs)
- [Physical Kinematic Model & Calibration](#-physical-kinematic-model--calibration)
- [Software Applications Suite](#-software-applications-suite)
  - [1. All-in-One Desktop GUI Studio (`roarm_gui.py`)](#1-all-in-one-desktop-gui-studio-roarm_guipy)
  - [2. Hand-Teaching & Waypoint Sequencer (`roarm_record_play_gui.py`)](#2-hand-teaching--waypoint-sequencer-roarm_record_play_guipy)
  - [3. Dedicated Serial Protocol Console (`roarm_serial_console.py`)](#3-dedicated-serial-protocol-console-roarm_serial_consolepy)
  - [4. WebSerial Browser Dashboard (`demos/demo_web_dashboard.html`)](#4-webserial-browser-dashboard-demosdemo_web_dashboardhtml)
  - [5. Python Driver SDK (`demos/roarm_driver.py`)](#5-python-driver-sdk-demosroarm_driverpy)
  - [6. Automated Motion Demonstrator (`demos/demo_motions.py`)](#6-automated-motion-demonstrator-demosdemo_motionspy)
  - [7. ROS 2 Control Integration (`src/roarm` & `src/serial_ctrl`)](#7-ros-2-control-integration-srcroarm--srcserial_ctrl)
- [Quick Start Guide](#-quick-start-guide)
  - [Hardware Setup & Serial Permissions](#hardware-setup--serial-permissions)
  - [Running the Applications](#running-the-applications)
- [Complete JSON Serial Protocol Reference](#-complete-json-serial-protocol-reference)
- [Troubleshooting & Hardware Tips](#-troubleshooting--hardware-tips)

---

## ⚙️ Overview & Hardware Specs

The **Waveshare RoArm-M1** is a 5-Degree-of-Freedom desktop articulated robotic arm designed for educational, research, and light automation workflows.

```
                           [Joint 4: Wrist Pitch]
                                     O=====[Joint 5: Gripper Clamp]
                                    /
             [Joint 3: Elbow]      / (Forearm Link L3: 130mm)
                    O-------------+
                   /
                  / (Upper Arm Link L2: 130mm)
                 /
 [Joint 2: Shoulder]
        O
        | (Base Height L1: 123mm)
   +----+----+
   | Joint 1 | (Base Pan 360° Rotation)
   +---------+
```

### Technical Specifications
- **Controller Board:** Onboard ESP32 MCU with integrated Wi-Fi (802.11 b/g/n) and Bluetooth 4.2 BLE.
- **Actuators:** 5× High-Torque ST3215 Serial Bus Servos (30 kg·cm stall torque, 12-bit magnetic encoders with 4096 steps/rev).
- **Communication:** USB-to-UART bridge (CP2102/CH340), 115200 baud default, `8-N-1`.
- **Operating Voltage:** 12V DC (5A power supply recommended).
- **Degrees of Freedom (DOF):** 5 Active Axes (Base Pan, Shoulder, Elbow, Wrist Pitch, Gripper Clamp).
- **End-Effector:** Two-finger parallel clamp gripper with integrated rubber grip pads.

---

## 📐 Physical Kinematic Model & Calibration

Every joint on the RoArm-M1 has been calibrated against physical hardware behavior to ensure 100% agreement between screen visualizers, Cartesian mathematics, and real-world arm positions:

| Joint | Axis Name | Physical Range | Zero Reference / Calibration Truth | Positive (+) Motion Direction |
| :---: | :--- | :---: | :--- | :--- |
| **J1** | **Base Pan** | `0.0°` to `360.0°` | **`180.0°`** is centered forward | Counter-Clockwise (CCW) rotation looking from top |
| **J2** | **Shoulder** | `-90.0°` to `+90.0°` | **`0.0°`** is **True Vertical Straight UP** | Tilts arm forward toward table; negative tilts backward |
| **J3** | **Elbow** | `0.0°` to `180.0°` | **`90.0°`** is horizontal forward | Increasing angle bends forearm **DOWN** toward table |
| **J4** | **Wrist Pitch** | `-30.0°` to `+115.0°` | **`0.0°`** is **Straight Level** (collinear with forearm)<br>**`90.0°`** is **Straight DOWN** (perpendicular) | Increasing angle tilts tool downwards toward table |
| **J5** | **Gripper Clamp** | `180.0°` to `360.0°` | **`180.0°`** = **Fully OPEN**<br>**`270.0°`** = **Half Grip**<br>**`360.0°`** = **Fully CLOSED** | Increasing angle pinches claws shut |

> [!IMPORTANT]
> **Cartesian Center Reference Pose (`T: 12`)**
> The factory calibrated Cartesian neutral position corresponds to:
> - **Joint Angles:** `P1 = 180.0°`, `P2 = 0.0°`, `P3 = 90.0°`, `P4 = 90.0°`, `P5 = 180.0°`
> - **3D Coordinates:** $X = 277.51\text{ mm},\; Y = -13.75\text{ mm},\; Z = 276.58\text{ mm},\; \text{Pitch }\Theta = 90.0^\circ$

---

## 💻 Software Applications Suite

```
RoArm-M1 Software Architecture
 ├── roarm_gui.py                   -> All-in-One Desktop GUI Studio (Kinematics, Sliders, Demos)
 ├── roarm_record_play_gui.py       -> Hand-Teaching & Trajectory Sequencer Studio
 ├── roarm_serial_console.py        -> Bidirectional Protocol Console & Command Studio
 ├── serial_gui.py                  -> Lightweight Raw Serial Monitor
 ├── demos/
 │    ├── roarm_driver.py           -> Reusable Python Driver (Hardware abstraction layer)
 │    ├── demo_motions.py           -> 7-Step Physical Hardware Demo & Test Suite
 │    ├── demo_interactive.py       -> Interactive CLI Keyboard Jogger
 │    ├── demo_web_dashboard.html   -> In-Browser WebSerial Real-time Dashboard
 │    ├── demo_wifi_http.py         -> Wireless ESP32 Wi-Fi REST API Client
 │    ├── ros2_demo_publisher.py    -> ROS 2 JointState Trajectory Publisher
 │    └── piching mholdeer.json     -> Example Recorded Trajectory Routine
 └── src/
      ├── roarm/                    -> ROS 2 URDF, Meshes, RViz2 Visualizer & Launchers
      └── serial_ctrl/              -> ROS 2 to ST3215 Serial Bridge Node
```

### 1. All-in-One Desktop GUI Studio (`roarm_gui.py`)
A comprehensive desktop workstation designed in a modern dark-mode aesthetic:
- **Dual Vector Visualizers:**
  - *Side Elevation Profile:* Real-time 2D kinematic arm rendering showing link lengths, joints, and claw spread.
  - *Top-Down Compass Dial:* Displays base rotation azimuth (0°–360°).
- **Physical Sliders:** Precision control of J1 through J5 with automatic hardware boundary clamping.
- **Cartesian IK Commander:** Command target coordinates ($X, Y, Z$ in mm, $\Theta$ pitch) solved directly by the arm's onboard inverse kinematics engine (`T: 2`).
- **Quick Action Triggers:** 1-click Emergency Stop (`T: 0`), Calibrated Angle Home (`T: 11`), Cartesian Center Reset (`T: 12`), Gripper Open (`180°`), and Gripper Close (`360°`).
- **Preset Demonstration Routines:** Waving salute and full Pick-and-Place sequence.
- **One-Click Studio Launchers:** Dedicated shortcut buttons to open the **Record & Play Studio** and **Serial Command Console**.

```bash
python3 roarm_gui.py
```

---

### 2. Hand-Teaching & Waypoint Sequencer (`roarm_record_play_gui.py`)
A dedicated trajectory programming suite allowing users to teach the robot physical tasks by guiding it with their hands:
- **Torque Toggle:** 
  - 🔓 **Torque OFF (`T: 8, P1: 0`):** Relaxes motors so you can position the arm by hand.
  - 🔒 **Torque ON (`T: 8, P1: 1`):** Re-engages holding torque instantly.
- **Waypoint Capture:**
  - **Single Snapshot (Spacebar shortcut):** Reads current joint telemetry and inserts a waypoint into the timeline.
  - **Live Stream Recording (🔴 10 Hz):** Continuously records smooth manual trajectory paths.
  - **Pause Insertion:** Add deliberate waiting delays between movements.
- **Sequence Timeline Table:**
  - Reorder waypoints with Move Up / Move Down buttons.
  - In-place editing of joint angles, motion durations, and wait delays.
  - Single-step execution ("Test Step") to verify poses individually.
- **Playback Deck:**
  - Speed Multiplier slider ($0.5\times$ to $2.0\times$ speed).
  - Play, Pause, Resume, and Stop controls.
  - Continuous loop mode for automated endurance testing or repetitive workcell tasks.
- **Persistence & Firmware Sync:**
  - Save and load routine sequences as readable `.json` files (e.g. `demos/piching mholdeer.json`).
  - Write sequences directly into ESP32 onboard Flash memory (`T: 8, P1: 5`) and trigger standalone onboard replay (`T: 8, P1: 6`).

```bash
python3 roarm_record_play_gui.py
```

---

### 3. Dedicated Serial Protocol Console (`roarm_serial_console.py`)
An interactive serial studio and protocol analyzer tailored specifically for the RoArm-M1 firmware:
- **Port Selector & Auto-Unlocker:** Scans active ports (`/dev/ttyUSB*`, `/dev/ttyACM*`) with integrated `fuser -k` port-release utility to kill lingering processes blocking the serial bus.
- **Live Bidirectional Terminal:** Color-coded terminal display with green TX packets, cyan RX telemetry, amber system alerts, and red errors.
- **Preset Library:** One-click triggers for Emergency Stop, Homing, Cartesian Center, Servo Telemetry query, Gripper actions, and Wrist Pitch angles (`-20°` Up, `0°` Level, `45°` Down, `90°` Straight Down).
- **Visual JSON Command Builder:** Interactive form to construct valid commands for `T: 1` (Joints), `T: 2` (Cartesian), `T: 3` (Raw Ticks), and `T: 8` (Torque).
- **Macro & Script Runner:** Paste or load multi-line commands with `# delay <seconds>` directives for automated script execution.
- **Live Telemetry Banner:** Top cards displaying real-time joint angles, servo loads, and connection status.

```bash
python3 roarm_serial_console.py
```

---

### 4. WebSerial Browser Dashboard (`demos/demo_web_dashboard.html`)
A standalone web application requiring **no installation or server backend**:
- Runs in Google Chrome, Microsoft Edge, or Opera using the native **WebSerial API**.
- Direct USB connection over WebSerial at 115200 baud with a single button click.
- Real-time SVG vector rendering of arm links, elevation angles, and gripper spread.
- Interactive joint sliders, Cartesian IK coordinate inputs, and one-click demo presets.

```bash
# Launch directly in browser:
google-chrome demos/demo_web_dashboard.html
# or
xdg-open demos/demo_web_dashboard.html
```

---

### 5. Python Driver SDK (`demos/roarm_driver.py`)
The reusable hardware abstraction library powering the automated demos:
- Thread-safe serial communication with automated port detection.
- Methods:
  - `arm.set_joint_angles(p1, p2, p3, p4, p5, speed=200, acc=60)`
  - `arm.set_cartesian_coords(x, y, z, theta=90.0, gripper=180.0, step_delay=10)`
  - `arm.open_gripper()`, `arm.close_gripper()`, `arm.set_gripper(angle)`
  - `arm.reset_joint_angles()` (`T: 11`), `arm.reset_cartesian_coords()` (`T: 12`)
  - `arm.set_torque(enable=True)` (`T: 8`)
  - `arm.get_servo_telemetry()` (`T: 5`)

```python
from roarm_driver import RoArmM1

# Connect to physical arm
arm = RoArmM1(port="/dev/ttyUSB0", baudrate=115200)

# Move to home stance
arm.reset_joint_angles(wait=1.0)

# Move in Cartesian space (X=250mm, Y=0mm, Z=150mm, Pitch=90° straight down)
arm.set_cartesian_coords(250.0, 0.0, 150.0, theta=90.0, gripper=180.0)

# Grasp payload
arm.close_gripper(wait=0.8)

# Safe disconnect
arm.close()
```

---

### 6. Automated Motion Demonstrator (`demos/demo_motions.py`)
A comprehensive, non-interactive 7-step physical validation suite:
1. **Diagnostics:** Queries ESP32 hardware information and ST3215 servo health.
2. **Neutral Alignment:** Homes all joints to calibrated neutral stance (`T: 11`).
3. **Gripper Cycle:** Cycles gripper clamp from open (180°) to closed (360°) and back.
4. **Base Sweep:** Smooth continuous rotation across Joint 1 (180° $\to$ 90° $\to$ 270° $\to$ 180°).
5. **Elevation & Waving:** Raises shoulder/elbow and waves wrist back and forth.
6. **3D Cartesian Pick-and-Place:** Hover, descend, grip, lift, traverse, deposit, release, and retract using inverse kinematics.
7. **Safe Park:** Returns arm to compact, low-strain parked position.

```bash
# Run single pass
python3 demos/demo_motions.py --port /dev/ttyUSB0

# Run continuous loop for exhibitions/burn-in testing
python3 demos/demo_motions.py --port /dev/ttyUSB0 --loop
```

---

### 7. ROS 2 Control Integration (`src/roarm` & `src/serial_ctrl`)
A complete ROS 2 package suite:
- **`roarm` Package:** Provides URDF kinematic model, 3D mesh files, RViz2 visualizer configuration, and launch files.
- **`serial_ctrl` Package:** C++ / Python ROS 2 node that subscribes to `/joint_states` and translates radian angles to RoArm-M1 `T: 3` raw servo steps over serial UART.
- **`demos/ros2_demo_publisher.py`:** Standalone trajectory generator publishing smooth multi-joint spline paths to `/joint_states`.

```bash
# Terminal 1: Launch RViz2 and Robot State Publisher
ros2 launch roarm roarm.launch.py gui:=False

# Terminal 2: Run the Serial Bridge to the physical arm
ros2 run serial_ctrl serial_ctrl --ros-args -p serial_port:=/dev/ttyUSB0

# Terminal 3: Publish automated motion trajectories
python3 demos/ros2_demo_publisher.py
```

---

## 🚀 Quick Start Guide

### Hardware Setup & Serial Permissions

1. Connect the **12V 5A DC power supply** to the DC barrel jack on the RoArm-M1 base board.
2. Connect the arm to your Linux PC via a **USB Type-C cable**.
3. Grant read/write permissions to serial ports:
   ```bash
   sudo usermod -a -G dialout $USER
   sudo chmod 666 /dev/ttyUSB* /dev/ttyACM*
   ```
   *(Log out and log back in for dialout group changes to take effect permanently).*

4. Install Python dependencies:
   ```bash
   pip install pyserial
   sudo apt-get install python3-tk
   ```

### Running the Applications

```bash
# 1. Launch the All-in-One Desktop Studio (Recommended)
python3 roarm_gui.py

# 2. Launch the Hand-Teaching Waypoint Sequencer
python3 roarm_record_play_gui.py

# 3. Launch the Serial Command Studio
python3 roarm_serial_console.py
```

---

## 📡 Complete JSON Serial Protocol Reference

All commands are sent as single-line JSON strings terminated by a newline (`\n`).

### 1. Joint Angle Control (`T: 1`)
Sets target angles for all 5 joints in degrees.
```json
{"T":1,"P1":180,"P2":0,"P3":90,"P4":90,"P5":180,"S1":300,"S2":300,"S3":300,"S4":300,"S5":300,"A1":60,"A2":60,"A3":60,"A4":60,"A5":60}
```
- `P1`–`P5`: Target angles in degrees.
- `S1`–`S5`: Servo velocity (0–3000, recommended: 200–500).
- `A1`–`A5`: Servo acceleration (0–255, recommended: 60).

### 2. Cartesian Space IK Control (`T: 2`)
Moves tool end-effector to target 3D Cartesian coordinates using onboard Inverse Kinematics.
```json
{"T":2,"P1":277.5,"P2":-13.8,"P3":276.6,"P4":90.0,"P5":180.0,"S1":10,"S5":200}
```
- `P1` ($X$ in mm), `P2` ($Y$ in mm), `P3` ($Z$ in mm).
- `P4` ($\Theta$ Tool Pitch Angle in degrees: `0°` = level, `90°` = straight down).
- `P5` (Gripper Clamp: `180°` = open, `360°` = closed).
- `S1`: Interpolation delay per step in milliseconds (lower is faster).
- `S5`: Gripper servo speed.

### 3. Raw Servo Position (`T: 3`)
Directly commands magnetic encoder steps to the ST3215 bus servos (0–4095 ticks, center is 2047).
```json
{"T":3,"P1":2047,"P2":2047,"P3":2047,"P4":2047,"P5":2047,"S1":0,"S2":0,"S3":0,"S4":0,"S5":0,"A1":60,"A2":60,"A3":60,"A4":60,"A5":60}
```

### 4. Telemetry & Diagnostics Queries
| Type | Purpose | Command | Response Format |
| :---: | :--- | :--- | :--- |
| **`T: 4`** | Device & Network Information | `{"T": 4}` | `{"name":"RoArm-M1","mac":"...","mode":"AP"}` |
| **`T: 5`** | Live Angles & Servo Motor Loads | `{"T": 5}` | `{"A1":180.0,"L1":12,"A2":0.0,"L2":-35,...}` |
| **`T: 105`** | Fast Joint Angle Feedback | `{"T": 105}` | `{"P1":180.0,"P2":0.0,"P3":90.0,"P4":90.0,"P5":180.0}` |

### 5. Initialization & Homing
| Type | Purpose | Command | Notes |
| :---: | :--- | :--- | :--- |
| **`T: 0`** | **Emergency Stop** | `{"T": 0}` | Cuts motor power immediately |
| **`T: 11`** | Angle Neutral Calibration Stance | `{"T": 11}` | `P1=180, P2=0, P3=90, P4=90, P5=180` |
| **`T: 12`** | Cartesian Initial Center Position | `{"T": 12}` | $X=277.5, Y=-13.8, Z=276.6, \Theta=90^\circ$ |

### 6. Hand-Teaching & Onboard Flash Storage (`T: 8`)
| Action | Command | Explanation |
| :--- | :--- | :--- |
| **Torque OFF** | `{"T": 8, "P1": 0}` | Unlocks servos so the arm can be moved freely by hand |
| **Torque ON** | `{"T": 8, "P1": 1}` | Re-locks servos to hold current position |
| **Save Step to Flash** | `{"T": 8, "P1": 5, "P2": 1, "P3": 5}` | Saves current pose as Step 1 with a 5-second duration |
| **Replay from Flash** | `{"T": 8, "P1": 6, "P2": 500, "P3": 1}` | Replays stored sequence at speed 500 in loop mode |

---

## 🛠️ Troubleshooting & Hardware Tips

### 1. Serial Port Busy (`Errno 16: Device or resource busy`)
If another terminal, script, or ROS node is holding `/dev/ttyUSB0` open:
```bash
# Identify and terminate the blocking process:
fuser -k /dev/ttyUSB0
```
*Note: The **Serial Command Studio (`roarm_serial_console.py`)** features a built-in "Unlock Port" button that executes this automatically.*

### 2. Joint 2 Underflow Quirk
In the ESP32 firmware, Joint 2 uses the formula `(P2 + 15) * 3`. Commanding an angle $P_2 < -14^\circ$ can cause an unsigned integer wrap-around. All Python drivers and GUI sliders in this suite enforce `P2 >= -14.0°` to prevent sudden mechanical over-rotation.

### 3. Power Supply Voltage Drop
If servos jitter, reboot, or drop communication during high-acceleration moves, check that the DC power supply is delivering a steady 12V with at least 5A capacity.

---

## 📄 License
This development suite is licensed under the Apache 2.0 / MIT License. Open-source models and meshes courtesy of Waveshare Electronics.
