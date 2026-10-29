#!/usr/bin/env python3
"""
Waveshare RoArm-M1 Desktop GUI Controller (Stable Physical Version)
===================================================================
A clean, stable, standalone desktop graphical user interface to control
the physical Waveshare RoArm-M1 robotic arm.

Features:
- Live Kinematic Visualizer (Side Profile + Top-Down Base Pan Compass Dial)
- Direct Joint Sliders with Rate-Limited Hardware Commands
- Quick Action Buttons (Gripper Open/Close, Home, Cartesian IK)
- One-Click Physical Demonstrations (Wave Hello, Pick & Place, Base Scan, Dance)
- Torque Release / Lock for Hand Teaching
- Clean Serial Communication without background telemetry collisions

Usage:
    python3 roarm_gui.py
    python3 roarm_gui.py --port /dev/ttyUSB0
"""

import sys
import os
import time
import math
import json
import threading
import argparse
import subprocess
from typing import Optional, Dict, Any

import tkinter as tk
from tkinter import ttk, messagebox

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


# ==============================================================================
# Pure Physical Hardware Driver
# ==============================================================================
class RoArmDriver:
    """Thread-safe serial driver for Waveshare RoArm-M1."""

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.ser: Optional[serial.Serial] = None
        self.lock = threading.Lock()
        self.is_connected = False

    def connect(self) -> bool:
        if not HAS_SERIAL:
            raise RuntimeError("pyserial is not installed! Run: pip install pyserial")

        with self.lock:
            # Free port if locked by a background monitor process
            try:
                out = subprocess.check_output(["fuser", self.port], stderr=subprocess.DEVNULL).decode().strip()
                for pid in out.split():
                    subprocess.run(["kill", "-9", pid], check=False)
                time.sleep(0.3)
            except Exception:
                pass

            try:
                self.ser = serial.Serial(self.port, self.baudrate, timeout=0.8)
                time.sleep(1.0)  # ESP32 serial reset stabilization
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self.is_connected = True
                return True
            except Exception as e:
                self.is_connected = False
                raise ConnectionError(f"Cannot open {self.port}: {e}")

    def disconnect(self):
        with self.lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.is_connected = False

    def send_cmd(self, cmd_dict: Dict[str, Any], wait_reply: bool = False, timeout: float = 0.8) -> Optional[Dict[str, Any]]:
        with self.lock:
            if not self.ser or not self.ser.is_open:
                return None
            try:
                payload = json.dumps(cmd_dict) + "\n"
                self.ser.write(payload.encode("utf-8"))
                self.ser.flush()

                if wait_reply:
                    start_t = time.time()
                    while time.time() - start_t < timeout:
                        line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                        if line.startswith("{") and line.endswith("}"):
                            try:
                                return json.loads(line)
                            except json.JSONDecodeError:
                                pass
                return None
            except Exception as e:
                print(f"[Driver Error] Write error: {e}", file=sys.stderr)
                return None


# ==============================================================================
# Desktop GUI Application
# ==============================================================================
class RoArmGUI:
    def __init__(self, root: tk.Tk, default_port: str = "/dev/ttyUSB0"):
        self.root = root
        self.root.title("Waveshare RoArm-M1 Studio")
        self.root.geometry("1180x820")
        self.root.minsize(1050, 750)

        # Style palette (Sleek Dark Theme)
        self.c_bg = "#0b1329"
        self.c_card = "#16203c"
        self.c_card_border = "#2a375a"
        self.c_text = "#f8fafc"
        self.c_muted = "#94a3b8"
        self.c_cyan = "#06b6d4"
        self.c_blue = "#3b82f6"
        self.c_green = "#10b981"
        self.c_red = "#ef4444"
        self.c_amber = "#f59e0b"

        self.root.configure(bg=self.c_bg)

        # Driver
        self.driver = RoArmDriver(port=default_port)

        # State variables - True physical RoArm-M1 neutral angles
        self.is_ready = False
        self.canvas = None
        self.log_text = None
        self.val_labels = []
        self.sliders = []
        # P1: Base pan, P2: Shoulder, P3: Elbow, P4: Wrist, P5: Gripper
        self.current_angles = [180.0, 0.0, 90.0, 90.0, 180.0]
        self.current_coords = [277.5, -13.8, 276.6, 90.0]  # X, Y, Z, Theta
        self.torque_on = True
        self.running_routine = False
        self.routine_stop_event = threading.Event()
        self._updating_programmatically = False

        # Build Interface
        self._setup_styles()
        self._build_top_bar()
        self._build_main_content()
        self._build_bottom_bar()

        self.is_ready = True
        self._update_arm_visualizer()

        # Auto-connect attempt after UI draws
        self.root.after(300, self._initial_connect)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Horizontal.TScale",
                        background=self.c_card,
                        troughcolor="#0f172a",
                        sliderthickness=16)

        style.configure("TCombobox",
                        fieldbackground=self.c_card,
                        background=self.c_card,
                        foreground=self.c_text)

    # --------------------------------------------------------------------------
    # Top Header & Connection Bar
    # --------------------------------------------------------------------------
    def _build_top_bar(self):
        header = tk.Frame(self.root, bg="#0d1835", height=65, padx=20, pady=10)
        header.pack(fill=tk.X, side=tk.TOP)

        brand_frame = tk.Frame(header, bg="#0d1835")
        brand_frame.pack(side=tk.LEFT)

        icon_lbl = tk.Label(brand_frame, text="🦾", font=("Segoe UI Emoji", 24), bg="#0d1835")
        icon_lbl.pack(side=tk.LEFT, padx=(0, 10))

        title_box = tk.Frame(brand_frame, bg="#0d1835")
        title_box.pack(side=tk.LEFT)

        title_lbl = tk.Label(title_box, text="Waveshare RoArm-M1 Studio",
                             font=("Inter", 15, "bold"), fg=self.c_text, bg="#0d1835")
        title_lbl.pack(anchor="w")

        sub_lbl = tk.Label(title_box, text="5-DOF High-Torque ST3215 Serial Bus Servo Robotic Arm",
                           font=("Inter", 8), fg=self.c_muted, bg="#0d1835")
        sub_lbl.pack(anchor="w")

        conn_frame = tk.Frame(header, bg="#0d1835")
        conn_frame.pack(side=tk.RIGHT)

        tk.Label(conn_frame, text="Port:", font=("Inter", 9), fg=self.c_muted, bg="#0d1835").pack(side=tk.LEFT, padx=4)
        self.port_combo = ttk.Combobox(conn_frame, width=14, values=["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"])
        self.port_combo.set(self.driver.port)
        self.port_combo.pack(side=tk.LEFT, padx=6)

        self.btn_refresh = tk.Button(conn_frame, text="🔄", command=self._refresh_ports,
                                     bg="#1e293b", fg=self.c_text, relief=tk.FLAT, padx=6, pady=3)
        self.btn_refresh.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_connect = tk.Button(conn_frame, text="🔌 Connect", command=self._toggle_connect,
                                     bg=self.c_blue, fg="#ffffff", font=("Inter", 9, "bold"),
                                     relief=tk.FLAT, padx=14, pady=5, cursor="hand2")
        self.btn_connect.pack(side=tk.LEFT, padx=6)

        self.btn_estop = tk.Button(conn_frame, text="🛑 E-STOP", command=self._emergency_stop,
                                   bg=self.c_red, fg="#ffffff", font=("Inter", 10, "bold"),
                                   relief=tk.FLAT, padx=14, pady=5, cursor="hand2")
        self.btn_estop.pack(side=tk.LEFT, padx=(10, 0))

    # --------------------------------------------------------------------------
    # Main Content Area: 3 Columns
    # --------------------------------------------------------------------------
    def _build_main_content(self):
        container = tk.Frame(self.root, bg=self.c_bg, padx=16, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        col_left = tk.Frame(container, bg=self.c_card, highlightbackground=self.c_card_border,
                            highlightthickness=1, padx=16, pady=16)
        col_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10), ipadx=4)

        col_mid = tk.Frame(container, bg=self.c_card, highlightbackground=self.c_card_border,
                           highlightthickness=1, padx=16, pady=16)
        col_mid.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        col_right = tk.Frame(container, bg=self.c_card, highlightbackground=self.c_card_border,
                             highlightthickness=1, padx=16, pady=16)
        col_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, ipadx=4)

        self._build_joint_panel(col_left)
        self._build_visualizer_panel(col_mid)
        self._build_routines_panel(col_right)

    # --------------------------------------------------------------------------
    # Column 1: Joint & Cartesian Control
    # --------------------------------------------------------------------------
    def _build_joint_panel(self, parent):
        tk.Label(parent, text="🎛️ JOINT ANGLE CONTROLS (T: 1)", font=("Inter", 11, "bold"),
                 fg=self.c_cyan, bg=self.c_card).pack(anchor="w", pady=(0, 12))

        self.sliders = []
        self.val_labels = []

        joint_specs = [
            ("Joint 1 (Base Pan)", 0, 360, 180),
            ("Joint 2 (Shoulder: 0° Vertical)", -90, 90, 0),
            ("Joint 3 (Elbow)", 0, 180, 90),
            ("Joint 4 (Wrist: 0° Level, 90° Down)", -30, 115, 90),
            ("Joint 5 (Gripper: 180° Open, 360° Close)", 180, 360, 180),
        ]

        for i, (name, min_v, max_v, init_v) in enumerate(joint_specs):
            box = tk.Frame(parent, bg=self.c_card)
            box.pack(fill=tk.X, pady=6)

            header = tk.Frame(box, bg=self.c_card)
            header.pack(fill=tk.X)

            tk.Label(header, text=name, font=("Inter", 9), fg=self.c_text, bg=self.c_card).pack(side=tk.LEFT)
            val_lbl = tk.Label(header, text=f"{init_v:.1f}°", font=("JetBrains Mono", 9, "bold"),
                               fg=self.c_cyan, bg=self.c_card)
            val_lbl.pack(side=tk.RIGHT)
            self.val_labels.append(val_lbl)

            row = tk.Frame(box, bg=self.c_card)
            row.pack(fill=tk.X, pady=(2, 0))

            btn_sub = tk.Button(row, text="◀", font=("Inter", 8), width=2, bg="#1e293b", fg=self.c_text,
                                relief=tk.FLAT, command=lambda idx=i, d=-5: self._step_joint(idx, d))
            btn_sub.pack(side=tk.LEFT, padx=(0, 4))

            slider = ttk.Scale(row, from_=min_v, to=max_v, orient=tk.HORIZONTAL,
                               style="Horizontal.TScale",
                               command=lambda val, idx=i: self._on_slider_drag(idx, val))
            slider.set(init_v)
            slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.sliders.append(slider)

            btn_add = tk.Button(row, text="▶", font=("Inter", 8), width=2, bg="#1e293b", fg=self.c_text,
                                relief=tk.FLAT, command=lambda idx=i, d=5: self._step_joint(idx, d))
            btn_add.pack(side=tk.LEFT, padx=(4, 0))

        # Gripper Quick Buttons
        grip_box = tk.Frame(parent, bg=self.c_card)
        grip_box.pack(fill=tk.X, pady=(12, 16))

        tk.Button(grip_box, text="🔓 Open Gripper (180°)", bg="#1e293b", fg=self.c_text, font=("Inter", 9),
                  relief=tk.FLAT, command=lambda: self._set_gripper(180)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        tk.Button(grip_box, text="🔒 Close Gripper (360°)", bg="#1e293b", fg=self.c_text, font=("Inter", 9),
                  relief=tk.FLAT, command=lambda: self._set_gripper(360)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # Cartesian Inputs (T: 2)
        sep = tk.Frame(parent, height=1, bg=self.c_card_border)
        sep.pack(fill=tk.X, pady=(4, 12))

        tk.Label(parent, text="📐 CARTESIAN POSITION (T: 2)", font=("Inter", 11, "bold"),
                 fg=self.c_cyan, bg=self.c_card).pack(anchor="w", pady=(0, 8))

        c_grid = tk.Frame(parent, bg=self.c_card)
        c_grid.pack(fill=tk.X, pady=4)

        labels = ["X (mm)", "Y (mm)", "Z (mm)", "Theta (°)"]
        self.cart_entries = []

        for r in range(2):
            for c in range(2):
                idx = r * 2 + c
                cell = tk.Frame(c_grid, bg=self.c_card)
                cell.grid(row=r, column=c, padx=4, pady=4, sticky="ew")
                tk.Label(cell, text=labels[idx], font=("Inter", 8), fg=self.c_muted, bg=self.c_card).pack(anchor="w")
                entry = tk.Entry(cell, font=("JetBrains Mono", 9), bg="#0f172a", fg="#ffffff",
                                 relief=tk.FLAT, insertbackground="#fff", width=10)
                entry.insert(0, str(self.current_coords[idx]))
                entry.pack(fill=tk.X, pady=2)
                self.cart_entries.append(entry)

        c_grid.columnconfigure(0, weight=1)
        c_grid.columnconfigure(1, weight=1)

        tk.Button(parent, text="🚀 Send Cartesian Pose (IK)", bg=self.c_blue, fg="#ffffff",
                  font=("Inter", 9, "bold"), relief=tk.FLAT, pady=6, cursor="hand2",
                  command=self._send_cartesian_target).pack(fill=tk.X, pady=(8, 2))

        tk.Button(parent, text="🎯 Reset to Cartesian Center (T: 12)", bg="#1e293b", fg=self.c_cyan,
                  font=("Inter", 8, "bold"), relief=tk.FLAT, pady=5, cursor="hand2",
                  command=self._home_cartesian).pack(fill=tk.X, pady=(2, 0))

    # --------------------------------------------------------------------------
    # Column 2: Kinematic Visualizer & Protocol Stream
    # --------------------------------------------------------------------------
    def _build_visualizer_panel(self, parent):
        top_row = tk.Frame(parent, bg=self.c_card)
        top_row.pack(fill=tk.X, pady=(0, 10))

        tk.Label(top_row, text="👁️ KINEMATIC PROFILE & VISUALIZER", font=("Inter", 11, "bold"),
                 fg=self.c_cyan, bg=self.c_card).pack(side=tk.LEFT)

        self.telemetry_label = tk.Label(top_row, text="Hardware: Ready", font=("JetBrains Mono", 9),
                                        fg=self.c_green, bg=self.c_card)
        self.telemetry_label.pack(side=tk.RIGHT)

        # SVG/Vector Canvas
        self.canvas_w = 540
        self.canvas_h = 350
        self.canvas = tk.Canvas(parent, width=self.canvas_w, height=self.canvas_h,
                                bg="#060c1d", highlightthickness=1, highlightbackground=self.c_card_border)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self._draw_canvas_grid()

        # Terminal / JSON Log
        tk.Label(parent, text="📡 SERIAL PROTOCOL STREAM", font=("Inter", 9, "bold"),
                 fg=self.c_muted, bg=self.c_card).pack(anchor="w", pady=(10, 4))

        log_frame = tk.Frame(parent, bg=self.c_card)
        log_frame.pack(fill=tk.X)

        self.log_text = tk.Text(log_frame, height=7, bg="#050814", fg="#38bdf8",
                                font=("JetBrains Mono", 8), relief=tk.FLAT, wrap=tk.WORD)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def _draw_canvas_grid(self):
        if not self.canvas:
            return
        self.canvas.delete("grid")
        for x in range(0, self.canvas_w, 25):
            self.canvas.create_line(x, 0, x, self.canvas_h, fill="#0f1c3f", tags="grid")
        for y in range(0, self.canvas_h, 25):
            self.canvas.create_line(0, y, self.canvas_w, y, fill="#0f1c3f", tags="grid")
        self.canvas.create_line(20, 280, self.canvas_w - 20, 280, fill="#334155", width=3, tags="grid")

    def _update_arm_visualizer(self):
        """Draws realistic, fully bounded arm kinematics with live side & top dials."""
        if self.canvas is None:
            return
        self.canvas.delete("arm")

        a1 = self.current_angles[0]
        a2 = self.current_angles[1]
        a3 = self.current_angles[2]
        a4 = self.current_angles[3]
        a5 = self.current_angles[4]

        # -------------------------------------------------------------
        # 1. SIDE ELEVATION ARM PROFILE (Joints 2, 3, 4, 5)
        # -------------------------------------------------------------
        base_x = 200
        base_y = 280
        l1 = 45   # Base riser
        l2 = 85   # Shoulder link
        l3 = 80   # Forearm link
        l4 = 45   # Wrist / tool link

        # Proper RoArm kinematics math:
        # Joint 2 (Shoulder): 0° is straight vertical UP (90° from ground)
        rad2 = math.radians(90.0 - a2)

        # Joint 3 (Elbow): 90° is horizontal forward; increasing bends DOWN
        rad3 = rad2 - math.radians(a3)

        # Joint 4 (Wrist/Gripper Pitch): 0° is straight level, 90° is straight down
        rad4 = rad3 - math.radians(a4)

        p0 = (base_x, base_y)
        p1 = (base_x, base_y - l1)
        p2 = (p1[0] + l2 * math.cos(rad2), p1[1] - l2 * math.sin(rad2))
        p3 = (p2[0] + l3 * math.cos(rad3), p2[1] - l3 * math.sin(rad3))
        p4 = (p3[0] + l4 * math.cos(rad4), p3[1] - l4 * math.sin(rad4))

        # Base pedestal
        self.canvas.create_rectangle(base_x - 30, base_y - 12, base_x + 30, base_y,
                                     fill="#1e293b", outline=self.c_cyan, width=1.5, tags="arm")

        # Links
        self.canvas.create_line(p0[0], p0[1], p1[0], p1[1], fill="#64748b", width=12, capstyle=tk.ROUND, tags="arm")
        self.canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill=self.c_blue, width=10, capstyle=tk.ROUND, tags="arm")
        self.canvas.create_line(p2[0], p2[1], p3[0], p3[1], fill=self.c_cyan, width=8, capstyle=tk.ROUND, tags="arm")
        self.canvas.create_line(p3[0], p3[1], p4[0], p4[1], fill="#8b5cf6", width=6, capstyle=tk.ROUND, tags="arm")

        # Gripper Claws (Joint 5: 180° open, 360° closed)
        open_ratio = max(0.0, min(1.0, (360.0 - a5) / 180.0))
        spread_rad = math.radians(open_ratio * 35.0)
        claw_len = 20
        c1 = (p4[0] + claw_len * math.cos(rad4 - 0.2 - spread_rad),
              p4[1] - claw_len * math.sin(rad4 - 0.2 - spread_rad))
        c2 = (p4[0] + claw_len * math.cos(rad4 + 0.2 + spread_rad),
              p4[1] - claw_len * math.sin(rad4 + 0.2 + spread_rad))

        self.canvas.create_line(p4[0], p4[1], c1[0], c1[1], fill=self.c_amber, width=4, capstyle=tk.ROUND, tags="arm")
        self.canvas.create_line(p4[0], p4[1], c2[0], c2[1], fill=self.c_amber, width=4, capstyle=tk.ROUND, tags="arm")

        # Joint Knots
        knots = [
            (p0, "#0f172a", 6),
            (p1, self.c_cyan, 7),
            (p2, self.c_blue, 6),
            (p3, self.c_cyan, 5),
            (p4, self.c_amber, 5)
        ]
        for pt, col, r in knots:
            self.canvas.create_oval(pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r,
                                    fill=col, outline="#ffffff", width=1.5, tags="arm")

        # Elevation Label
        self.canvas.create_text(base_x - 110, base_y + 15, text="SIDE ELEVATION PROFILE",
                                fill=self.c_muted, font=("Inter", 8, "bold"), tags="arm")

        # -------------------------------------------------------------
        # 2. TOP-DOWN BASE ROTATION COMPASS DIAL (Joint 1)
        # -------------------------------------------------------------
        dial_cx = 455
        dial_cy = 70
        dial_r = 42

        self.canvas.create_oval(dial_cx - dial_r, dial_cy - dial_r,
                                dial_cx + dial_r, dial_cy + dial_r,
                                fill="#0d1835", outline=self.c_card_border, width=2, tags="arm")
        self.canvas.create_oval(dial_cx - 4, dial_cy - 4, dial_cx + 4, dial_cy + 4,
                                fill=self.c_cyan, outline="#fff", tags="arm")

        pan_rad = math.radians(a1 - 90.0)
        nx = dial_cx + (dial_r - 8) * math.cos(pan_rad)
        ny = dial_cy + (dial_r - 8) * math.sin(pan_rad)
        self.canvas.create_line(dial_cx, dial_cy, nx, ny, fill=self.c_cyan, width=3.5, arrow=tk.LAST, tags="arm")

        self.canvas.create_text(dial_cx, dial_cy - dial_r - 10, text="TOP: BASE PAN",
                                fill=self.c_cyan, font=("Inter", 8, "bold"), tags="arm")
        self.canvas.create_text(dial_cx, dial_cy + dial_r + 10, text=f"J1 = {a1:.1f}°",
                                fill=self.c_text, font=("JetBrains Mono", 8), tags="arm")

    # --------------------------------------------------------------------------
    # Column 3: Physical Demo Routines & Calibration
    # --------------------------------------------------------------------------
    def _build_routines_panel(self, parent):
        tk.Label(parent, text="⚡ PHYSICAL MOTION DEMOS", font=("Inter", 11, "bold"),
                 fg=self.c_cyan, bg=self.c_card).pack(anchor="w", pady=(0, 12))

        demos = [
            ("👋 Wave Greeting", self._launch_routine_wave, self.c_blue),
            ("📦 Pick & Place", self._launch_routine_pick_place, self.c_cyan),
            ("🔄 Base 180° Scan", self._launch_routine_scan, "#8b5cf6"),
            ("💃 Dynamic Dance", self._launch_routine_dance, "#ec4899"),
            ("🏠 Home Neutral (T: 11)", self._home_neutral, "#334155"),
            ("📐 Cartesian Init (T: 12)", self._home_cartesian, "#334155"),
        ]

        for text, cmd, col in demos:
            btn = tk.Button(parent, text=text, command=cmd, bg=col, fg="#ffffff",
                            font=("Inter", 9, "bold"), relief=tk.FLAT, pady=8, cursor="hand2")
            btn.pack(fill=tk.X, pady=4)

        sep = tk.Frame(parent, height=1, bg=self.c_card_border)
        sep.pack(fill=tk.X, pady=(12, 12))

        tk.Label(parent, text="🛠️ SERVO TORQUE & TELEMETRY", font=("Inter", 10, "bold"),
                 fg=self.c_muted, bg=self.c_card).pack(anchor="w", pady=(0, 6))

        self.btn_torque = tk.Button(parent, text="🔓 Unlock Torque (Hand Teach)",
                                    command=self._toggle_torque, bg="#1e293b", fg=self.c_text,
                                    font=("Inter", 9), relief=tk.FLAT, pady=7, cursor="hand2")
        self.btn_torque.pack(fill=tk.X, pady=4)

        tk.Button(parent, text="📊 Read Arm Telemetry (T: 5)", command=self._read_telemetry_safe,
                  bg="#1e293b", fg=self.c_cyan, font=("Inter", 9, "bold"), relief=tk.FLAT, pady=7, cursor="hand2").pack(fill=tk.X, pady=4)

        tk.Button(parent, text="🎙️ Open Record & Play Studio", command=self._launch_record_play,
                  bg="#065f46", fg="#a7f3d0", font=("Inter", 9, "bold"), relief=tk.FLAT, pady=7, cursor="hand2").pack(fill=tk.X, pady=(8, 4))

        tk.Button(parent, text="⚡ Open Serial Command Studio", command=self._launch_serial_studio,
                  bg="#1e3a8a", fg="#bfdbfe", font=("Inter", 9, "bold"), relief=tk.FLAT, pady=7, cursor="hand2").pack(fill=tk.X, pady=4)

    def _launch_record_play(self):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roarm_record_play_gui.py")
        subprocess.Popen([sys.executable, script])

    def _launch_serial_studio(self):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roarm_serial_console.py")
        subprocess.Popen([sys.executable, script])

    # --------------------------------------------------------------------------
    # Bottom Status Bar
    # --------------------------------------------------------------------------
    def _build_bottom_bar(self):
        bar = tk.Frame(self.root, bg="#0d1835", height=32, padx=16, pady=6)
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_dot = tk.Label(bar, text="●", font=("Inter", 12), fg=self.c_red, bg="#0d1835")
        self.status_dot.pack(side=tk.LEFT, padx=(0, 6))

        self.status_msg = tk.Label(bar, text="Disconnected", font=("Inter", 9), fg=self.c_muted, bg="#0d1835")
        self.status_msg.pack(side=tk.LEFT)

        author_lbl = tk.Label(bar, text="RoArm-M1 Physical Hardware Active • 115200 Baud",
                              font=("Inter", 8), fg="#64748b", bg="#0d1835")
        author_lbl.pack(side=tk.RIGHT)

    def _log(self, text: str):
        if getattr(self, "log_text", None):
            self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {text}\n")
            self.log_text.see(tk.END)
        else:
            print(f"[{time.strftime('%H:%M:%S')}] {text}")

    # --------------------------------------------------------------------------
    # Connection Logic
    # --------------------------------------------------------------------------
    def _refresh_ports(self):
        if not HAS_SERIAL:
            return
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            ports = ["/dev/ttyUSB0", "/dev/ttyACM0"]
        self.port_combo["values"] = ports
        self._log(f"Detected ports: {ports}")

    def _initial_connect(self):
        self._toggle_connect(auto=True)

    def _toggle_connect(self, auto: bool = False):
        if self.driver.is_connected:
            self.driver.disconnect()
            self.btn_connect.config(text="🔌 Connect", bg=self.c_blue)
            self.status_dot.config(fg=self.c_red)
            self.status_msg.config(text="Disconnected", fg=self.c_muted)
            self._log("Disconnected from serial port.")
        else:
            port = self.port_combo.get().strip()
            self.driver.port = port
            try:
                self.driver.connect()
                self.btn_connect.config(text="🔌 Disconnect", bg="#1e293b")
                self.status_dot.config(fg=self.c_green)
                self.status_msg.config(text=f"Connected to {port} (115200 baud)", fg=self.c_green)
                self._log(f"Successfully connected to physical RoArm-M1 on {port}!")
                # Align physical arm to Home
                self.root.after(300, self._home_neutral)
            except Exception as e:
                self.status_dot.config(fg=self.c_red)
                self.status_msg.config(text=f"Connection failed: {e}", fg=self.c_red)
                self._log(f"Connection failed: {e}")
                if not auto:
                    messagebox.showerror("Connection Error", str(e))

    # --------------------------------------------------------------------------
    # Synchronized Pose Setter
    # --------------------------------------------------------------------------
    def set_pose(self, j1: float, j2: float, j3: float, j4: float, j5: float,
                 send_hardware: bool = True, update_sliders: bool = True, speed: int = 250):
        """Unified method to update joint angles across UI, Canvas, and Physical Hardware."""
        self.current_angles = [float(j1), float(j2), float(j3), float(j4), float(j5)]

        if update_sliders and len(self.sliders) >= 5 and len(self.val_labels) >= 5:
            self._updating_programmatically = True
            for idx in range(5):
                self.sliders[idx].set(self.current_angles[idx])
                self.val_labels[idx].config(text=f"{self.current_angles[idx]:.1f}°")
            self._updating_programmatically = False

        self._update_arm_visualizer()

        if send_hardware and self.driver.is_connected:
            cmd = {
                "T": 1,
                "P1": round(self.current_angles[0], 2),
                "P2": max(-14.0, round(self.current_angles[1], 2)),
                "P3": round(self.current_angles[2], 2),
                "P4": round(self.current_angles[3], 2),
                "P5": round(self.current_angles[4], 2),
                "S1": speed, "S2": speed, "S3": speed, "S4": speed, "S5": speed,
                "A1": 60, "A2": 60, "A3": 60, "A4": 60, "A5": 60
            }
            self.driver.send_cmd(cmd)

    def _on_slider_drag(self, idx: int, val_str: str):
        if not getattr(self, "is_ready", False) or getattr(self, "_updating_programmatically", False):
            return
        val = float(val_str)
        self.current_angles[idx] = val
        if idx < len(self.val_labels):
            self.val_labels[idx].config(text=f"{val:.1f}°")

        self._update_arm_visualizer()

        if not hasattr(self, "_last_send_t"):
            self._last_send_t = 0
        now = time.time()
        if now - self._last_send_t > 0.10:
            self._send_current_angles(speed=250)
            self._last_send_t = now

    def _step_joint(self, idx: int, delta: float):
        cur = self.current_angles[idx]
        new_v = max(self.sliders[idx]["from"], min(self.sliders[idx]["to"], cur + delta))
        self.sliders[idx].set(new_v)
        self._on_slider_drag(idx, str(new_v))
        self._send_current_angles(speed=200)

    def _set_gripper(self, angle: float):
        self.sliders[4].set(angle)
        self._on_slider_drag(4, str(angle))
        self._send_current_angles(speed=300)

    def _send_current_angles(self, speed: int = 200, acc: int = 60):
        cmd = {
            "T": 1,
            "P1": round(self.current_angles[0], 2),
            "P2": round(self.current_angles[1], 2),
            "P3": round(self.current_angles[2], 2),
            "P4": round(self.current_angles[3], 2),
            "P5": round(self.current_angles[4], 2),
            "S1": speed, "S2": speed, "S3": speed, "S4": speed, "S5": speed,
            "A1": acc, "A2": acc, "A3": acc, "A4": acc, "A5": acc
        }
        self.driver.send_cmd(cmd)
        self._log(f"TX: {json.dumps(cmd)}")

    def _send_cartesian_target(self):
        try:
            x = float(self.cart_entries[0].get())
            y = float(self.cart_entries[1].get())
            z = float(self.cart_entries[2].get())
            theta = float(self.cart_entries[3].get())
        except ValueError:
            messagebox.showwarning("Input Error", "Please enter valid floating point numbers for X, Y, Z, Theta.")
            return

        cmd = {
            "T": 2,
            "P1": x, "P2": y, "P3": z, "P4": theta,
            "P5": self.current_angles[4],
            "S1": 10, "S5": 200
        }
        self.driver.send_cmd(cmd)
        self._log(f"TX (Cartesian IK): {json.dumps(cmd)}")

    def _home_neutral(self):
        cmd = {"T": 11}
        self.driver.send_cmd(cmd)
        self._log("TX: {\"T\": 11} -> Moving to Angle Home Pose (Cartesian Center)")
        self.set_pose(180, 0, 90, 90, 180, send_hardware=False, update_sliders=True)
        self._sync_cartesian_entries([277.5, -13.8, 276.6, 90.0])

    def _home_cartesian(self):
        cmd = {"T": 12}
        self.driver.send_cmd(cmd)
        self._log("TX: {\"T\": 12} -> Moving to Cartesian Center (X=277.5, Y=-13.8, Z=276.6, Theta=90.0°)")
        self.set_pose(180, 0, 90, 90, 180, send_hardware=False, update_sliders=True)
        self._sync_cartesian_entries([277.5, -13.8, 276.6, 90.0])

    def _sync_cartesian_entries(self, coords):
        self.current_coords = list(coords)
        for i, val in enumerate(coords):
            if i < len(self.cart_entries):
                self.cart_entries[i].delete(0, tk.END)
                self.cart_entries[i].insert(0, str(val))

    def _toggle_torque(self):
        self.torque_on = not self.torque_on
        val = 1 if self.torque_on else 0
        cmd = {"T": 8, "P1": val}
        self.driver.send_cmd(cmd)
        self.btn_torque.config(text="🔓 Unlock Torque (Hand Teach)" if self.torque_on else "🔒 Lock Torque (Torque ON)")
        self._log(f"Torque set to {'ON' if self.torque_on else 'OFF (Unlocked for teaching)'}")

    def _emergency_stop(self):
        self.routine_stop_event.set()
        cmd = {"T": 0}
        self.driver.send_cmd(cmd)
        self.torque_on = False
        self.btn_torque.config(text="🔒 Lock Torque (Torque ON)")
        self._log("🛑 EMERGENCY STOP TRIGGERED! Torques disabled.")

    def _read_telemetry_safe(self):
        """Safely reads physical servo telemetry (T:5) on demand without collisions."""
        if not self.driver.is_connected:
            return
        res = self.driver.send_cmd({"T": 5}, wait_reply=True, timeout=0.8)
        if res:
            # Check that this is actual T:5 feedback (contains T1 load field)
            if "T1" in res and "A1" in res:
                j1 = float(res.get("A1", self.current_angles[0]))
                j2 = float(res.get("A2", self.current_angles[1]))
                j3 = float(res.get("A3", self.current_angles[2]))
                j4 = float(res.get("A4", self.current_angles[3]))
                j5 = float(res.get("A5", self.current_angles[4]))
                self._log(f"RX Telemetry: J1={j1:.1f}° J2={j2:.1f}° J3={j3:.1f}° J4={j4:.1f}° J5={j5:.1f}°")
                self.telemetry_label.config(
                    text=f"J1:{j1:.0f}° J2:{j2:.0f}° J3:{j3:.0f}° J4:{j4:.0f}° J5:{j5:.0f}°",
                    fg=self.c_green
                )
            elif "P1" in res:
                # T:1 echo response: positions are in P1..P5!
                j1 = float(res.get("P1", self.current_angles[0]))
                j2 = float(res.get("P2", self.current_angles[1]))
                j3 = float(res.get("P3", self.current_angles[2]))
                j4 = float(res.get("P4", self.current_angles[3]))
                j5 = float(res.get("P5", self.current_angles[4]))
                self._log(f"RX Echo: P1={j1:.1f}° P2={j2:.1f}° P3={j3:.1f}° P4={j4:.1f}° P5={j5:.1f}°")

    # --------------------------------------------------------------------------
    # Threaded Demo Routines
    # --------------------------------------------------------------------------
    def _run_in_thread(self, target_func):
        if self.running_routine:
            return
        self.running_routine = True
        self.routine_stop_event.clear()

        def worker():
            try:
                target_func()
            finally:
                self.running_routine = False

        threading.Thread(target=worker, daemon=True).start()

    def _launch_routine_wave(self):
        def routine():
            self._log("[DEMO] Starting Wave Greeting Routine...")
            # Step 1: Raise shoulder and forearm
            self.root.after(0, lambda: self.set_pose(180, 45, 60, 100, 180, speed=250))
            time.sleep(1.3)

            for i in range(3):
                if self.routine_stop_event.is_set():
                    break
                # Wave Left
                self.root.after(0, lambda: self.set_pose(205, 45, 60, 120, 180, speed=350))
                time.sleep(0.6)
                # Wave Right
                self.root.after(0, lambda: self.set_pose(155, 45, 60, 80, 180, speed=350))
                time.sleep(0.6)

            # Return to Home
            self.root.after(0, lambda: self.set_pose(180, 0, 90, 90, 180, speed=200))
            self._log("[DEMO] Wave finished.")
        self._run_in_thread(routine)

    def _launch_routine_pick_place(self):
        def routine():
            self._log("[DEMO] Running Pick & Place Sequence...")
            steps = [
                (150, 20, 70, 80, 180, "1. Hovering above pickup point", 1.3),
                (150, 40, 90, 70, 180, "2. Lowering to grasp object", 1.1),
                (150, 40, 90, 70, 360, "3. Clamping gripper around object", 0.9),
                (150, 10, 60, 90, 360, "4. Lifting object to transfer altitude", 1.3),
                (210, 10, 60, 90, 360, "5. Swinging Base across to drop station", 1.5),
                (210, 40, 90, 70, 360, "6. Lowering to deposit height", 1.1),
                (210, 40, 90, 70, 180, "7. Releasing gripper clamp", 0.9),
                (210, 10, 60, 90, 180, "8. Ascending to safe clearance", 1.1),
                (180, 0,  90, 90, 180, "9. Returning home", 1.3),
            ]

            for s in steps:
                if self.routine_stop_event.is_set():
                    break
                self._log(f"-> {s[5]}")
                self.root.after(0, lambda p=s: self.set_pose(p[0], p[1], p[2], p[3], p[4], speed=250))
                time.sleep(s[6])

            self._log("[DEMO] Pick & Place complete.")
        self._run_in_thread(routine)

    def _launch_routine_scan(self):
        def routine():
            self._log("[DEMO] Running Base 180° Sweep...")
            self.root.after(0, lambda: self.set_pose(230, 0, 90, 90, 180, speed=200))
            time.sleep(1.6)
            self.root.after(0, lambda: self.set_pose(130, 0, 90, 90, 180, speed=200))
            time.sleep(1.8)
            self.root.after(0, lambda: self.set_pose(180, 0, 90, 90, 180, speed=200))
            self._log("[DEMO] Base sweep complete.")
        self._run_in_thread(routine)

    def _launch_routine_dance(self):
        def routine():
            self._log("[DEMO] Robotic Dance Sequence...")
            dance_poses = [
                (160, 30, 45, 110, 120),
                (200, 15, 100, 70, 180),
                (170, 40, 40, 120, 95),
                (190, 0,  90, 90,  180)
            ]
            for p in dance_poses:
                if self.routine_stop_event.is_set():
                    break
                self.root.after(0, lambda pose=p: self.set_pose(pose[0], pose[1], pose[2], pose[3], pose[4], speed=300))
                time.sleep(0.9)

            self.root.after(0, lambda: self.set_pose(180, 0, 90, 90, 180, speed=200))
            self._log("[DEMO] Dance complete.")
        self._run_in_thread(routine)


def main():
    parser = argparse.ArgumentParser(description="Waveshare RoArm-M1 GUI Studio")
    parser.add_argument("--port", type=str, default="/dev/ttyUSB0", help="Serial port (default: /dev/ttyUSB0)")
    args = parser.parse_args()

    root = tk.Tk()
    app = RoArmGUI(root, default_port=args.port)

    def on_closing():
        app.routine_stop_event.set()
        app.driver.disconnect()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
