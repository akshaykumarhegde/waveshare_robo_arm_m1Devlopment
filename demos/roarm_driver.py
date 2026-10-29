#!/usr/bin/env python3
"""
Waveshare RoArm-M1 Python Driver
================================
Supports USB Serial communication (115200 baud) and Simulated/Mock mode.
Implements the full RoArm-M1 ESP32 JSON protocol (T:0 to T:13).

Author: Antigravity Assistant
Compatible with: Waveshare RoArm-M1 (ESP32 + ST3215 Bus Servos)
"""

import sys
import time
import json
import logging
from typing import Optional, Dict, Any, Tuple

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s - %(message)s')
logger = logging.getLogger("RoArmM1")


class RoArmM1:
    """Python API controller for the Waveshare RoArm-M1 robotic arm."""

    # Default kinematic parameters (mm) from RoArm-M1 firmware:
    LEN_A = 115.432   # Base to shoulder vertical offset
    LEN_B = 41.0513   # Base to shoulder horizontal offset
    LEN_C = 168.8579  # Shoulder to elbow arm length
    LEN_D = 127.9234  # Elbow to wrist forearm length
    LEN_E = 108.5357  # Wrist to end effector length
    LEN_F = 7.7076    # Tool center vertical offset
    LEN_H = -13.75    # Shoulder Y offset

    INIT_X = LEN_B + LEN_D + LEN_E   # ~ 277.51 mm
    INIT_Y = LEN_H                   # ~ -13.75 mm
    INIT_Z = LEN_A + LEN_C - LEN_F   # ~ 276.58 mm
    INIT_T = 90.0                    # Pitch angle (deg)

    # Gripper angle boundaries (deg: 180° = Open, 360° = Close)
    GRIPPER_OPEN = 180.0
    GRIPPER_CLOSED = 360.0

    def __init__(self, port: Optional[str] = None, baudrate: int = 115200, timeout: float = 1.0, mock: bool = False):
        """
        Initialize RoArm-M1 controller.
        
        :param port: Serial port path (e.g. '/dev/ttyUSB0', 'COM3'). If None, attempts auto-detection.
        :param baudrate: Baud rate (default: 115200).
        :param timeout: Serial read timeout in seconds.
        :param mock: If True, operates in simulation/mock mode without physical hardware.
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_mock = mock
        self.ser: Optional[Any] = None

        # Internal state tracking
        self.current_angles = [180.0, 0.0, 90.0, 90.0, 180.0]  # Joints 1 to 5
        self.current_coords = [self.INIT_X, self.INIT_Y, self.INIT_Z, self.INIT_T, self.GRIPPER_OPEN]
        self.torque_enabled = True

        if not self.is_mock:
            self._connect()

    def _auto_detect_port(self) -> Optional[str]:
        """Auto-detect likely RoArm-M1 USB serial port."""
        if not HAS_SERIAL:
            return None
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            return None
        
        # Priority for known USB UART identifiers (ESP32, CP210x, CH340, FTDI)
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if any(k in desc or k in hwid for k in ["cp210", "ch340", "ftdi", "usb serial", "esp32"]):
                return p.device
        
        # Fall back to first ttyUSB or ttyACM or COM port
        for p in ports:
            if "ttyusb" in p.device.lower() or "ttyacm" in p.device.lower() or "com" in p.device.lower():
                return p.device
        return ports[0].device

    def _connect(self):
        """Establish serial communication to physical RoArm-M1."""
        if not HAS_SERIAL:
            raise RuntimeError("pyserial is not installed. Run: pip install pyserial")

        if self.port is None:
            self.port = self._auto_detect_port()

        if self.port is None:
            raise ConnectionError(
                "No serial port detected! Please ensure the RoArm-M1 USB cable is plugged in, "
                "and /dev/ttyUSB0 or /dev/ttyACM0 is accessible."
            )

        try:
            logger.info(f"Connecting to physical RoArm-M1 on {self.port} at {self.baudrate} baud...")
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(1.2)  # Allow ESP32 serial stabilization
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            logger.info(f"Successfully connected to physical RoArm-M1 on {self.port}!")
        except serial.SerialException as e:
            if "Device or resource busy" in str(e) or "Errno 16" in str(e):
                # Attempt to find and kill locking process (e.g. serial-monitor)
                import subprocess
                try:
                    out = subprocess.check_output(["fuser", self.port], stderr=subprocess.DEVNULL).decode().strip()
                    pids = out.split()
                    for pid in pids:
                        subprocess.run(["kill", "-9", pid], check=False)
                    time.sleep(0.5)
                    self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
                    self.ser.reset_input_buffer()
                    self.ser.reset_output_buffer()
                    logger.info(f"Released busy port {self.port} and connected successfully!")
                    return
                except Exception:
                    pass
            raise ConnectionError(
                f"Failed to open physical serial port '{self.port}': {e}\n"
                f"Tip: If another process (like Arduino IDE serial monitor) is open, close it first,\n"
                f"or run: sudo chmod 777 {self.port}"
            )

    def send_cmd(self, cmd_dict: Dict[str, Any], wait_response: bool = False, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """
        Send a JSON command dict to RoArm-M1 and optionally read the response.
        
        :param cmd_dict: Command dictionary e.g. {"T": 1, ...}
        :param wait_response: Whether to wait for a JSON response line.
        :param timeout: Time to wait for response in seconds.
        :return: Parsed response dict if available, else None.
        """
        cmd_str = json.dumps(cmd_dict) + "\n"
        
        if self.is_mock:
            logger.info(f"[MOCK SEND] {cmd_str.strip()}")
            # Return synthetic responses for queries
            t = cmd_dict.get("T")
            if t == 4:
                return {
                    "DevName": "RoArm-M1 (Simulated)",
                    "AP_SSID": "ESP32_DEV",
                    "STA_SSID": "WIFI_LOCAL",
                    "MAC": "AA:BB:CC:DD:EE:FF"
                }
            elif t == 5:
                return {
                    "A1": self.current_angles[0], "T1": 15,
                    "A2": self.current_angles[1], "T2": 22,
                    "A3": self.current_angles[2], "T3": 18,
                    "A4": self.current_angles[3], "T4": 12,
                    "A5": self.current_angles[4], "T5": 8
                }
            elif t == 1:
                for i in range(5):
                    k = f"P{i+1}"
                    if k in cmd_dict:
                        self.current_angles[i] = float(cmd_dict[k])
                return {"T": 1, **cmd_dict}
            elif t == 2:
                for i in range(5):
                    k = f"P{i+1}"
                    if k in cmd_dict:
                        self.current_coords[i] = float(cmd_dict[k])
                return {"T": 2, **cmd_dict}
            return {"status": "ok", "mock": True}

        if not self.ser or not self.ser.is_open:
            logger.error("Serial port is not open.")
            return None

        try:
            self.ser.write(cmd_str.encode('utf-8'))
            self.ser.flush()
            logger.debug(f"[SENT] {cmd_str.strip()}")

            if wait_response:
                start_time = time.time()
                while time.time() - start_time < timeout:
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        logger.debug(f"[RECV] {line}")
                        if line.startswith("{") and line.endswith("}"):
                            try:
                                return json.loads(line)
                            except json.JSONDecodeError:
                                pass
                return None
            return None
        except Exception as e:
            logger.error(f"Error during serial communication: {e}")
            return None

    # ==========================================
    # High-level Motion & Control APIs
    # ==========================================

    def emergency_stop(self):
        """Immediately release all motor torques and halt motion (T: 0)."""
        logger.warning("EMERGENCY STOP TRIGGERED!")
        self.send_cmd({"T": 0})
        self.torque_enabled = False

    def set_joint_angles(self, p1: float, p2: float, p3: float, p4: float, p5: float,
                         speed: int = 200, acc: int = 60, wait: float = 0.5) -> Optional[Dict[str, Any]]:
        """
        Move joints to specified angles in degrees (T: 1).
        
        :param p1: Base pan angle (0° - 360°, center is 180°)
        :param p2: Shoulder angle (large arm, reduced 1:3)
        :param p3: Elbow angle (small arm)
        :param p4: Wrist pitch / tilt
        :param p5: Gripper / EoAT clamp (180° open, 360° closed)
        :param speed: Servo speed 0-3000 (default: 200)
        :param acc: Acceleration 0-255 (default: 60)
        :param wait: Sleep duration after sending command (seconds)
        """
        cmd = {
            "T": 1,
            "P1": round(float(p1), 2),
            "P2": round(float(p2), 2),
            "P3": round(float(p3), 2),
            "P4": round(float(p4), 2),
            "P5": round(float(p5), 2),
            "S1": speed, "S2": speed, "S3": speed, "S4": speed, "S5": speed,
            "A1": acc, "A2": acc, "A3": acc, "A4": acc, "A5": acc
        }
        res = self.send_cmd(cmd, wait_response=True, timeout=0.8)
        self.current_angles = [p1, p2, p3, p4, p5]
        if wait > 0:
            time.sleep(wait)
        return res

    def reset_joint_angles(self, wait: float = 1.0):
        """Return joints to initial calibrated angle pose (T: 11)."""
        logger.info("Moving to Angle Init Pose (T: 11)...")
        self.send_cmd({"T": 11})
        self.current_angles = [180.0, 0.0, 90.0, 90.0, 180.0]
        if wait > 0:
            time.sleep(wait)

    def set_cartesian_coords(self, x: float, y: float, z: float, theta: float = 90.0,
                             gripper: float = 180.0, step_delay: int = 10,
                             gripper_speed: int = 200, wait: float = 0.5) -> Optional[Dict[str, Any]]:
        """
        Move end-effector to 3D Cartesian coordinates via Inverse Kinematics (T: 2).
        
        :param x: Target X position in mm
        :param y: Target Y position in mm
        :param z: Target Z position in mm
        :param theta: Tool pitch angle in degrees (default: 90.0)
        :param gripper: Gripper angle in degrees (180° = open, 360° = closed)
        :param step_delay: Delay per interpolation step in ms (smaller = faster motion)
        :param gripper_speed: Gripper servo speed (default: 200)
        :param wait: Sleep duration after sending command (seconds)
        """
        cmd = {
            "T": 2,
            "P1": round(float(x), 2),
            "P2": round(float(y), 2),
            "P3": round(float(z), 2),
            "P4": round(float(theta), 2),
            "P5": round(float(gripper), 2),
            "S1": int(step_delay),
            "S5": int(gripper_speed)
        }
        res = self.send_cmd(cmd, wait_response=True, timeout=1.0)
        self.current_coords = [x, y, z, theta, gripper]
        if wait > 0:
            time.sleep(wait)
        return res

    def reset_cartesian_coords(self, wait: float = 1.0):
        """Return end-effector to initial coordinate pose (T: 12)."""
        logger.info("Moving to Coordinate Init Pose (T: 12)...")
        self.send_cmd({"T": 12})
        self.current_coords = [self.INIT_X, self.INIT_Y, self.INIT_Z, self.INIT_T, self.GRIPPER_OPEN]
        if wait > 0:
            time.sleep(wait)

    def set_raw_positions(self, p1: int, p2: int, p3: int, p4: int, p5: int,
                          speed: int = 200, acc: int = 60, wait: float = 0.5) -> Optional[Dict[str, Any]]:
        """
        Direct raw servo position control in servo encoder ticks 0-4095 (T: 3).
        Middle center position is 2047.
        """
        cmd = {
            "T": 3,
            "P1": int(p1), "P2": int(p2), "P3": int(p3), "P4": int(p4), "P5": int(p5),
            "S1": speed, "S2": speed, "S3": speed, "S4": speed, "S5": speed,
            "A1": acc, "A2": acc, "A3": acc, "A4": acc, "A5": acc
        }
        res = self.send_cmd(cmd, wait_response=True, timeout=0.8)
        if wait > 0:
            time.sleep(wait)
        return res

    def reset_raw_positions(self, wait: float = 1.0):
        """Reset to raw ST servo center positions (T: 13)."""
        logger.info("Moving to Raw Position Init (T: 13)...")
        self.send_cmd({"T": 13})
        if wait > 0:
            time.sleep(wait)

    # ==========================================
    # Gripper Control Helpers
    # ==========================================

    def open_gripper(self, speed: int = 200, wait: float = 0.4):
        """Fully open the robotic gripper clamp."""
        self.current_angles[4] = self.GRIPPER_OPEN
        self.current_coords[4] = self.GRIPPER_OPEN
        return self.set_joint_angles(*self.current_angles, speed=speed, wait=wait)

    def close_gripper(self, speed: int = 200, wait: float = 0.4):
        """Close the robotic gripper clamp."""
        self.current_angles[4] = self.GRIPPER_CLOSED
        self.current_coords[4] = self.GRIPPER_CLOSED
        return self.set_joint_angles(*self.current_angles, speed=speed, wait=wait)

    def set_gripper(self, angle: float, speed: int = 200, wait: float = 0.4):
        """Set gripper to arbitrary opening angle between 180° (open) and 360° (closed)."""
        angle = max(180.0, min(360.0, angle))
        self.current_angles[4] = angle
        self.current_coords[4] = angle
        return self.set_joint_angles(*self.current_angles, speed=speed, wait=wait)

    # ==========================================
    # Telemetry and Information
    # ==========================================

    def get_device_info(self) -> Optional[Dict[str, Any]]:
        """Query device information, MAC, Wi-Fi configuration (T: 4)."""
        return self.send_cmd({"T": 4}, wait_response=True, timeout=1.0)

    def get_angles_and_torque(self) -> Optional[Dict[str, Any]]:
        """Query real-time angle positions and load/torque feedback for all 5 servos (T: 5)."""
        return self.send_cmd({"T": 5}, wait_response=True, timeout=1.0)

    def get_ik_buffer(self) -> Optional[Dict[str, Any]]:
        """Query internal inverse kinematics calculation buffer (T: 6)."""
        return self.send_cmd({"T": 6}, wait_response=True, timeout=1.0)

    # ==========================================
    # Torque and Teaching (Record & Replay)
    # ==========================================

    def set_torque(self, enable: bool = True):
        """
        Enable or disable servo torque locks.
        When torque is OFF, you can freely move the arm with your hands for demonstration / teaching.
        """
        val = 1 if enable else 0
        logger.info(f"Setting all servo torque: {'ENABLED' if enable else 'DISABLED'}")
        self.send_cmd({"T": 8, "P1": val})
        self.torque_enabled = enable

    def record_step(self, step_num: int, speed_delay: int = 5):
        """Save current arm pose to ESP32 Flash memory as step N (T: 8, P1: 5)."""
        logger.info(f"Recording current pose to step {step_num} (stride: {speed_delay})...")
        self.send_cmd({"T": 8, "P1": 5, "P2": int(step_num), "P3": int(speed_delay)})

    def move_to_step(self, step_num: int):
        """Move arm to a previously recorded step (T: 8, P1: 3)."""
        logger.info(f"Moving to recorded step {step_num}...")
        self.send_cmd({"T": 8, "P1": 3, "P2": int(step_num)})

    def replay_recorded_steps(self, step_delay: int = 500, loop_count: int = 1):
        """
        Replay all recorded steps saved in ESP32 memory.
        :param step_delay: Delay between steps in ms.
        :param loop_count: Number of repetitions (-1 for infinite).
        """
        logger.info(f"Replaying sequence (loops: {loop_count}, delay: {step_delay}ms)...")
        self.send_cmd({"T": 8, "P1": 6, "P2": int(step_delay), "P3": int(loop_count)})

    def close(self):
        """Close serial port."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info("Serial connection closed.")
