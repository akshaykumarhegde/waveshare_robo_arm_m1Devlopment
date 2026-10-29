#!/usr/bin/env python3
"""
================================================================================
Waveshare RoArm-M1 Teach & Play Studio (Record & Play GUI)
================================================================================
A dedicated, full-featured, user-friendly desktop GUI for:
- Hand-teaching: Unlock motor torques (Torque OFF) and physically pose the arm
- 1-Click Waypoint Capture (Capture live joint angles from physical robot)
- Live trajectory stream recording (record continuous fluid movements)
- Visual sequence editor (Reorder, edit, insert pauses, gripper actions)
- Smooth playback engine with speed multiplier (0.5x - 2.0x), loop mode, and pause
- Real-time 2D vector kinematics visualizer showing live arm pose
- File Manager: Save and load routine sequences (.json)
- Onboard ESP32 Flash Sync: Upload waypoints to hardware memory (T: 8)
================================================================================
"""

import sys
import os
import time
import json
import threading
import subprocess
import math
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("Error: pyserial is required. Install with: pip install pyserial")
    sys.exit(1)


class RoArmRecordPlayGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("RoArm-M1 Teach & Play Studio (Record & Play)")
        self.root.geometry("1180x820")
        self.root.minsize(1020, 700)

        # Color Theme: Dark Studio with Amber/Cyan/Green Accents
        self.c_bg = "#070c1b"
        self.c_card = "#0f172a"
        self.c_card_border = "#1e293b"
        self.c_input = "#030712"
        self.c_text = "#f8fafc"
        self.c_muted = "#94a3b8"
        self.c_cyan = "#06b6d4"
        self.c_blue = "#3b82f6"
        self.c_purple = "#8b5cf6"
        self.c_green = "#10b981"
        self.c_amber = "#f59e0b"
        self.c_red = "#ef4444"

        self.root.configure(bg=self.c_bg)

        # Serial Driver & State
        self.ser = None
        self.is_connected = False
        self.torque_enabled = True
        self.serial_lock = threading.Lock()

        # Arm Telemetry State (J1: Base, J2: Shoulder, J3: Elbow, J4: Wrist, J5: Gripper)
        # J2: 0° is straight vertical up, range -90° to +90°
        self.current_angles = [180.0, 0.0, 90.0, 90.0, 180.0]
        self.current_loads = [0, 0, 0, 0, 0]

        # Waypoint Sequence Data List
        # Each item: {"type": "pose"|"delay"|"gripper", "angles": [...], "duration": 1.0, "delay": 0.5, "note": ""}
        self.waypoints = []

        # Playback Engine State
        self.is_playing = False
        self.is_paused = False
        self.stop_playback_event = threading.Event()
        self.pause_playback_event = threading.Event()
        self.current_playing_index = -1
        self.loop_playback = tk.BooleanVar(value=False)
        self.speed_multiplier = tk.DoubleVar(value=1.0)

        # Stream Recording State
        self.is_stream_recording = False
        self.stop_stream_event = threading.Event()

        # Telemetry Background Poller
        self.stop_poller_event = threading.Event()

        # Build Interface
        self._setup_styles()
        self._build_top_bar()
        self._build_teach_banner()
        self._build_main_layout()
        self._build_player_bar()
        self._build_bottom_bar()

        # Window protocol
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Key Bindings
        self.root.bind("<space>", lambda e: self._capture_current_pose())

        # Auto-connect attempt
        self.root.after(400, self._auto_connect_default)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Treeview",
                        background=self.c_card,
                        fieldbackground=self.c_card,
                        foreground=self.c_text,
                        rowheight=26,
                        font=("JetBrains Mono", 9))
        style.configure("Treeview.Heading",
                        background="#1e293b",
                        foreground=self.c_cyan,
                        font=("Inter", 9, "bold"),
                        relief=tk.FLAT)
        style.map("Treeview",
                  background=[("selected", self.c_blue)],
                  foreground=[("selected", "#ffffff")])

        style.configure("TProgressbar",
                        background=self.c_cyan,
                        troughcolor="#0f172a",
                        borderwidth=0)

    # --------------------------------------------------------------------------
    # 1. Top Header & Connection Bar
    # --------------------------------------------------------------------------
    def _build_top_bar(self):
        bar = tk.Frame(self.root, bg="#0d1835", padx=16, pady=8)
        bar.pack(fill=tk.X, side=tk.TOP)

        left = tk.Frame(bar, bg="#0d1835")
        left.pack(side=tk.LEFT)

        tk.Label(left, text="🦾", font=("Segoe UI Emoji", 20), bg="#0d1835").pack(side=tk.LEFT, padx=(0, 8))
        tb = tk.Frame(left, bg="#0d1835")
        tb.pack(side=tk.LEFT)
        tk.Label(tb, text="RoArm-M1 Teach & Play Studio", font=("Inter", 13, "bold"),
                 fg=self.c_text, bg="#0d1835").pack(anchor="w")
        tk.Label(tb, text="Physical Hand-Teaching, Waypoint Sequencer & Trajectory Replay",
                 font=("Inter", 8), fg=self.c_muted, bg="#0d1835").pack(anchor="w")

        right = tk.Frame(bar, bg="#0d1835")
        right.pack(side=tk.RIGHT)

        tk.Label(right, text="Port:", font=("Inter", 9), fg=self.c_muted, bg="#0d1835").pack(side=tk.LEFT, padx=(4, 2))
        self.port_combo = ttk.Combobox(right, width=14, state="readonly")
        self.port_combo.pack(side=tk.LEFT, padx=2)
        self._refresh_ports()

        tk.Button(right, text="🔄", bg="#1e293b", fg=self.c_text, relief=tk.FLAT,
                  font=("Segoe UI Emoji", 8), command=self._refresh_ports).pack(side=tk.LEFT, padx=2)

        self.btn_connect = tk.Button(right, text="🔌 Connect", bg=self.c_green, fg="#ffffff",
                                     font=("Inter", 9, "bold"), relief=tk.FLAT, padx=12, pady=4,
                                     cursor="hand2", command=self._toggle_connection)
        self.btn_connect.pack(side=tk.LEFT, padx=(6, 4))

        tk.Button(right, text="🛑 E-Stop", bg=self.c_red, fg="#ffffff",
                  font=("Inter", 9, "bold"), relief=tk.FLAT, padx=10, pady=4,
                  cursor="hand2", command=self._emergency_stop).pack(side=tk.LEFT, padx=(4, 0))

    # --------------------------------------------------------------------------
    # 2. Teaching Mode & Torque Banner
    # --------------------------------------------------------------------------
    def _build_teach_banner(self):
        banner = tk.Frame(self.root, bg="#0b1329", padx=16, pady=8,
                          highlightthickness=1, highlightbackground=self.c_card_border)
        banner.pack(fill=tk.X, side=tk.TOP)

        # Status text & icon
        left = tk.Frame(banner, bg="#0b1329")
        left.pack(side=tk.LEFT)

        self.lbl_torque_status = tk.Label(
            left,
            text="🔒 MOTORS LOCKED (Torque ON) — Ready for playback or manual pose",
            font=("Inter", 10, "bold"),
            fg=self.c_green,
            bg="#0b1329"
        )
        self.lbl_torque_status.pack(anchor="w")

        # Big Hand-Teach Toggle Buttons
        right = tk.Frame(banner, bg="#0b1329")
        right.pack(side=tk.RIGHT)

        self.btn_torque_off = tk.Button(
            right,
            text="🔓 UNLOCK TORQUE (Hand-Teach)",
            bg="#b45309",
            fg="#fef3c7",
            font=("Inter", 9, "bold"),
            relief=tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
            command=lambda: self._set_torque(False)
        )
        self.btn_torque_off.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_torque_on = tk.Button(
            right,
            text="🔒 LOCK TORQUE",
            bg="#1e3a8a",
            fg="#dbeafe",
            font=("Inter", 9, "bold"),
            relief=tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
            command=lambda: self._set_torque(True)
        )
        self.btn_torque_on.pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            right,
            text="🏠 Home (T:11)",
            bg="#1e293b",
            fg=self.c_text,
            font=("Inter", 9),
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._home_robot
        ).pack(side=tk.LEFT)

    # --------------------------------------------------------------------------
    # 3. Main Workspace Layout: Left (Waypoints Table) | Right (Visualizer & Tools)
    # --------------------------------------------------------------------------
    def _build_main_layout(self):
        container = tk.Frame(self.root, bg=self.c_bg, padx=16, pady=8)
        container.pack(fill=tk.BOTH, expand=True)

        # Left Column: Capture bar + Waypoints Table
        left_col = tk.Frame(container, bg=self.c_card, highlightthickness=1,
                            highlightbackground=self.c_card_border, padx=12, pady=12)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        # Right Column: Live Arm Visualizer + Routine Presets + ESP32 Sync
        right_col = tk.Frame(container, bg=self.c_card, highlightthickness=1,
                             highlightbackground=self.c_card_border, width=440, padx=12, pady=12)
        right_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        right_col.pack_propagate(False)

        self._build_waypoint_controls(left_col)
        self._build_waypoint_table(left_col)
        self._build_visualizer_panel(right_col)

    # --------------------------------------------------------------------------
    # Left Column: Capture Toolbar & Waypoint List
    # --------------------------------------------------------------------------
    def _build_waypoint_controls(self, parent):
        top_row = tk.Frame(parent, bg=self.c_card)
        top_row.pack(fill=tk.X, pady=(0, 10))

        tk.Label(top_row, text="📋 SEQUENCE TIMELINE", font=("Inter", 11, "bold"),
                 fg=self.c_cyan, bg=self.c_card).pack(side=tk.LEFT)

        self.waypoint_count_lbl = tk.Label(top_row, text="0 steps", font=("JetBrains Mono", 9),
                                           fg=self.c_muted, bg=self.c_card)
        self.waypoint_count_lbl.pack(side=tk.RIGHT)

        # Big Capture Button Bar
        action_bar = tk.Frame(parent, bg=self.c_card)
        action_bar.pack(fill=tk.X, pady=(0, 10))

        # Primary Capture Button
        btn_cap = tk.Button(
            action_bar,
            text="📸 CAPTURE WAYPOINT (Space)",
            bg=self.c_blue,
            fg="#ffffff",
            font=("Inter", 10, "bold"),
            relief=tk.FLAT,
            padx=14,
            pady=8,
            cursor="hand2",
            command=self._capture_current_pose
        )
        btn_cap.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        # Add Pause
        tk.Button(
            action_bar,
            text="⏱️ Add Pause",
            bg="#1e293b",
            fg=self.c_text,
            font=("Inter", 9),
            relief=tk.FLAT,
            padx=8,
            pady=8,
            command=self._add_delay_dialog
        ).pack(side=tk.LEFT, padx=3)

        # Quick Gripper Open
        tk.Button(
            action_bar,
            text="🔓 Open Grip",
            bg="#1e293b",
            fg=self.c_amber,
            font=("Inter", 9, "bold"),
            relief=tk.FLAT,
            padx=8,
            pady=8,
            command=lambda: self._add_gripper_step(180.0, "Open Gripper")
        ).pack(side=tk.LEFT, padx=3)

        # Quick Gripper Close
        tk.Button(
            action_bar,
            text="🔒 Close Grip",
            bg="#1e293b",
            fg=self.c_amber,
            font=("Inter", 9, "bold"),
            relief=tk.FLAT,
            padx=8,
            pady=8,
            command=lambda: self._add_gripper_step(360.0, "Close Gripper")
        ).pack(side=tk.LEFT, padx=(3, 0))

        # Stream recording button
        self.btn_stream = tk.Button(
            action_bar,
            text="🔴 Stream Rec",
            bg="#450a0a",
            fg="#fca5a5",
            font=("Inter", 9, "bold"),
            relief=tk.FLAT,
            padx=8,
            pady=8,
            command=self._toggle_stream_recording
        )
        self.btn_stream.pack(side=tk.LEFT, padx=(6, 0))

    def _build_waypoint_table(self, parent):
        table_frame = tk.Frame(parent, bg=self.c_card)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("step", "type", "j1", "j2", "j3", "j4", "j5", "time", "note")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("step", text="#")
        self.tree.heading("type", text="Action Type")
        self.tree.heading("j1", text="J1 Base")
        self.tree.heading("j2", text="J2 Shoulder")
        self.tree.heading("j3", text="J3 Elbow")
        self.tree.heading("j4", text="J4 Wrist")
        self.tree.heading("j5", text="J5 Grip")
        self.tree.heading("time", text="Speed / Delay")
        self.tree.heading("note", text="Description")

        self.tree.column("step", width=36, anchor="center")
        self.tree.column("type", width=90, anchor="w")
        self.tree.column("j1", width=70, anchor="center")
        self.tree.column("j2", width=75, anchor="center")
        self.tree.column("j3", width=70, anchor="center")
        self.tree.column("j4", width=70, anchor="center")
        self.tree.column("j5", width=70, anchor="center")
        self.tree.column("time", width=85, anchor="center")
        self.tree.column("note", width=120, anchor="w")

        # Scrollbars
        v_scroll = tk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=v_scroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_waypoint_selected)
        self.tree.bind("<Double-1>", lambda e: self._move_arm_to_selected())

        # Table Management Toolbar
        row_tools = tk.Frame(parent, bg=self.c_card)
        row_tools.pack(fill=tk.X, pady=(10, 0))

        tk.Button(row_tools, text="🚀 Move Arm to Selected", bg=self.c_blue, fg="#ffffff",
                  font=("Inter", 8, "bold"), relief=tk.FLAT, padx=8, pady=4,
                  command=self._move_arm_to_selected).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(row_tools, text="✏️ Update Selected Pose", bg="#1e293b", fg=self.c_text,
                  font=("Inter", 8), relief=tk.FLAT, padx=6, pady=4,
                  command=self._update_selected_pose).pack(side=tk.LEFT, padx=3)

        tk.Button(row_tools, text="⬆️ Up", bg="#1e293b", fg=self.c_text, font=("Inter", 8),
                  relief=tk.FLAT, padx=6, pady=4, command=lambda: self._reorder_selected(-1)).pack(side=tk.LEFT, padx=3)

        tk.Button(row_tools, text="⬇️ Down", bg="#1e293b", fg=self.c_text, font=("Inter", 8),
                  relief=tk.FLAT, padx=6, pady=4, command=lambda: self._reorder_selected(1)).pack(side=tk.LEFT, padx=3)

        tk.Button(row_tools, text="🗑️ Delete", bg="#3b1d25", fg="#fca5a5", font=("Inter", 8),
                  relief=tk.FLAT, padx=6, pady=4, command=self._delete_selected).pack(side=tk.LEFT, padx=3)

        tk.Button(row_tools, text="🧹 Clear All", bg="#1e293b", fg=self.c_muted, font=("Inter", 8),
                  relief=tk.FLAT, padx=6, pady=4, command=self._clear_all_waypoints).pack(side=tk.RIGHT)

    # --------------------------------------------------------------------------
    # Right Column: Vector Arm Kinematics & Routine Sync
    # --------------------------------------------------------------------------
    def _build_visualizer_panel(self, parent):
        tk.Label(parent, text="👁️ LIVE ARM PROFILE", font=("Inter", 11, "bold"),
                 fg=self.c_cyan, bg=self.c_card).pack(anchor="w", pady=(0, 6))

        # Vector Canvas
        self.canvas_w = 416
        self.canvas_h = 280
        self.canvas = tk.Canvas(parent, width=self.canvas_w, height=self.canvas_h,
                                bg="#060c1d", highlightthickness=1,
                                highlightbackground=self.c_card_border)
        self.canvas.pack(fill=tk.X, pady=(0, 8))

        # Joint Readout Strip (J1..J5)
        strip = tk.Frame(parent, bg=self.c_card)
        strip.pack(fill=tk.X, pady=(0, 10))

        self.strip_labels = []
        short_names = ["J1 Base", "J2 Shld", "J3 Elbw", "J4 Wrst", "J5 Grip"]
        for name in short_names:
            cell = tk.Frame(strip, bg="#0f172a", highlightthickness=1,
                            highlightbackground=self.c_card_border, padx=4, pady=2)
            cell.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            tk.Label(cell, text=name, font=("Inter", 7), fg=self.c_muted, bg="#0f172a").pack()
            lbl = tk.Label(cell, text="--°", font=("JetBrains Mono", 8, "bold"),
                           fg=self.c_cyan, bg="#0f172a")
            lbl.pack()
            self.strip_labels.append(lbl)

        # File Routines & Presets Box
        sep = tk.Frame(parent, height=1, bg=self.c_card_border)
        sep.pack(fill=tk.X, pady=6)

        tk.Label(parent, text="💾 ROUTINE STORAGE & PRESETS", font=("Inter", 9, "bold"),
                 fg=self.c_text, bg=self.c_card).pack(anchor="w", pady=(2, 6))

        row_file = tk.Frame(parent, bg=self.c_card)
        row_file.pack(fill=tk.X, pady=2)

        tk.Button(row_file, text="💾 Save Routine (.json)", bg="#1e293b", fg=self.c_text,
                  font=("Inter", 8, "bold"), relief=tk.FLAT, pady=4,
                  command=self._save_routine_dialog).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        tk.Button(row_file, text="📂 Load Routine (.json)", bg="#1e293b", fg=self.c_text,
                  font=("Inter", 8, "bold"), relief=tk.FLAT, pady=4,
                  command=self._load_routine_dialog).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        # Sample Presets Dropdown
        row_preset = tk.Frame(parent, bg=self.c_card)
        row_preset.pack(fill=tk.X, pady=(6, 2))

        tk.Label(row_preset, text="Load Preset:", font=("Inter", 8), fg=self.c_muted, bg=self.c_card).pack(side=tk.LEFT)
        self.preset_combo = ttk.Combobox(row_preset, state="readonly", values=[
            "Wave Greeting Routine",
            "Pick-and-Place Demo",
            "Scanning Sweep Routine"
        ])
        self.preset_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        tk.Button(row_preset, text="Load", bg=self.c_blue, fg="#ffffff", font=("Inter", 8, "bold"),
                  relief=tk.FLAT, padx=8, command=self._load_selected_preset).pack(side=tk.LEFT)

        # Hardware ESP32 Flash Memory Sync (T: 8)
        sep2 = tk.Frame(parent, height=1, bg=self.c_card_border)
        sep2.pack(fill=tk.X, pady=8)

        tk.Label(parent, text="🤖 ROBOT ONBOARD FLASH (T: 8)", font=("Inter", 9, "bold"),
                 fg=self.c_purple, bg=self.c_card).pack(anchor="w", pady=(0, 4))

        row_flash = tk.Frame(parent, bg=self.c_card)
        row_flash.pack(fill=tk.X, pady=2)

        tk.Button(row_flash, text="📤 Upload to ESP32 Flash", bg="#312e81", fg="#c7d2fe",
                  font=("Inter", 8, "bold"), relief=tk.FLAT, pady=4,
                  command=self._upload_to_esp32_flash).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        tk.Button(row_flash, text="▶️ Hardware Replay", bg="#065f46", fg="#a7f3d0",
                  font=("Inter", 8, "bold"), relief=tk.FLAT, pady=4,
                  command=self._trigger_hardware_replay).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        self._draw_visualizer()

    def _draw_visualizer(self, ghost_angles=None):
        if not hasattr(self, "canvas") or not self.canvas:
            return
        self.canvas.delete("all")

        # Grid
        for x in range(0, self.canvas_w, 25):
            self.canvas.create_line(x, 0, x, self.canvas_h, fill="#0c1836")
        for y in range(0, self.canvas_h, 25):
            self.canvas.create_line(0, y, self.canvas_w, y, fill="#0c1836")
        self.canvas.create_line(20, 240, self.canvas_w - 20, 240, fill="#334155", width=2)

        base_x = 180
        base_y = 240
        l1 = 35   # Base riser
        l2 = 75   # Shoulder link
        l3 = 70   # Forearm link
        l4 = 40   # Wrist link

        # -------------------------------------------------------------
        # Draw Ghost Pose (if selected waypoint)
        # -------------------------------------------------------------
        if ghost_angles:
            g_a2, g_a3, g_a4, g_a5 = ghost_angles[1], ghost_angles[2], ghost_angles[3], ghost_angles[4]
            g_rad2 = math.radians(90.0 - g_a2)
            g_rad3 = g_rad2 - math.radians(g_a3)
            g_rad4 = g_rad3 - math.radians(g_a4)

            gp1 = (base_x, base_y - l1)
            gp2 = (gp1[0] + l2 * math.cos(g_rad2), gp1[1] - l2 * math.sin(g_rad2))
            gp3 = (gp2[0] + l3 * math.cos(g_rad3), gp2[1] - l3 * math.sin(g_rad3))
            gp4 = (gp3[0] + l4 * math.cos(g_rad4), gp3[1] - l4 * math.sin(g_rad4))

            self.canvas.create_line(gp1[0], gp1[1], gp2[0], gp2[1], fill="#38bdf8", width=3, dash=(4, 4))
            self.canvas.create_line(gp2[0], gp2[1], gp3[0], gp3[1], fill="#38bdf8", width=3, dash=(4, 4))
            self.canvas.create_line(gp3[0], gp3[1], gp4[0], gp4[1], fill="#38bdf8", width=2, dash=(4, 4))

        # -------------------------------------------------------------
        # Draw Live Arm Pose (Using user-verified kinematics!)
        # -------------------------------------------------------------
        a2 = self.current_angles[1]
        a3 = self.current_angles[2]
        a4 = self.current_angles[3]
        a5 = self.current_angles[4]

        # 1. Joint 2: 0° is straight vertical UP (90° from ground)
        rad2 = math.radians(90.0 - a2)

        # 2. Joint 3: 90° is horizontal forward; increasing bends DOWN
        rad3 = rad2 - math.radians(a3)

        # 3. Joint 4: 0° is straight level, 90° is straight down
        rad4 = rad3 - math.radians(a4)

        p0 = (base_x, base_y)
        p1 = (base_x, base_y - l1)
        p2 = (p1[0] + l2 * math.cos(rad2), p1[1] - l2 * math.sin(rad2))
        p3 = (p2[0] + l3 * math.cos(rad3), p2[1] - l3 * math.sin(rad3))
        p4 = (p3[0] + l4 * math.cos(rad4), p3[1] - l4 * math.sin(rad4))

        # Pedestal
        self.canvas.create_rectangle(base_x - 24, base_y - 8, base_x + 24, base_y,
                                     fill="#1e293b", outline=self.c_cyan, width=1.5)

        # Arm Links
        self.canvas.create_line(p0[0], p0[1], p1[0], p1[1], fill="#64748b", width=10, capstyle=tk.ROUND)
        self.canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill=self.c_blue, width=8, capstyle=tk.ROUND)
        self.canvas.create_line(p2[0], p2[1], p3[0], p3[1], fill=self.c_cyan, width=7, capstyle=tk.ROUND)
        self.canvas.create_line(p3[0], p3[1], p4[0], p4[1], fill=self.c_purple, width=5, capstyle=tk.ROUND)

        # Gripper Claws (Joint 5: 180° open, 360° closed)
        open_ratio = max(0.0, min(1.0, (360.0 - a5) / 180.0))
        spread_rad = math.radians(open_ratio * 35.0)
        claw_len = 16
        c1 = (p4[0] + claw_len * math.cos(rad4 - 0.25 - spread_rad),
              p4[1] - claw_len * math.sin(rad4 - 0.25 - spread_rad))
        c2 = (p4[0] + claw_len * math.cos(rad4 + 0.25 + spread_rad),
              p4[1] - claw_len * math.sin(rad4 + 0.25 + spread_rad))

        self.canvas.create_line(p4[0], p4[1], c1[0], c1[1], fill=self.c_amber, width=3, capstyle=tk.ROUND)
        self.canvas.create_line(p4[0], p4[1], c2[0], c2[1], fill=self.c_amber, width=3, capstyle=tk.ROUND)

        # Joint Dots
        for pt, col, r in [(p0, "#0f172a", 5), (p1, self.c_cyan, 6), (p2, self.c_blue, 5),
                           (p3, self.c_cyan, 5), (p4, self.c_amber, 4)]:
            self.canvas.create_oval(pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r,
                                    fill=col, outline="#ffffff", width=1.5)

        # Compass Dial for Joint 1 (Base Pan)
        dial_x = 360
        dial_y = 50
        dial_r = 24
        self.canvas.create_oval(dial_x - dial_r, dial_y - dial_r, dial_x + dial_r, dial_y + dial_r,
                                fill="#0f172a", outline=self.c_card_border, width=1.5)
        self.canvas.create_text(dial_x, dial_y - dial_r - 8, text="PAN (J1)", fill=self.c_muted, font=("Inter", 7))
        pan_rad = math.radians(self.current_angles[0] - 90.0)
        nx = dial_x + (dial_r - 4) * math.cos(pan_rad)
        ny = dial_y + (dial_r - 4) * math.sin(pan_rad)
        self.canvas.create_line(dial_x, dial_y, nx, ny, fill=self.c_cyan, width=2.5, arrow=tk.LAST)

    # --------------------------------------------------------------------------
    # 4. Playback Controller Bar (Bottom Deck)
    # --------------------------------------------------------------------------
    def _build_player_bar(self):
        player = tk.Frame(self.root, bg="#0d1835", padx=16, pady=10)
        player.pack(fill=tk.X, side=tk.BOTTOM)

        # Controls Left
        ctrl_left = tk.Frame(player, bg="#0d1835")
        ctrl_left.pack(side=tk.LEFT)

        self.btn_play = tk.Button(
            ctrl_left,
            text="▶️ PLAY SEQUENCE",
            bg=self.c_green,
            fg="#ffffff",
            font=("Inter", 11, "bold"),
            relief=tk.FLAT,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._start_playback
        )
        self.btn_play.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_pause = tk.Button(
            ctrl_left,
            text="⏸️ Pause",
            bg="#1e293b",
            fg=self.c_text,
            font=("Inter", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            pady=6,
            state=tk.DISABLED,
            command=self._toggle_pause_playback
        )
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_stop = tk.Button(
            ctrl_left,
            text="⏹️ Stop",
            bg="#7f1d1d",
            fg="#fecaca",
            font=("Inter", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            pady=6,
            state=tk.DISABLED,
            command=self._stop_playback
        )
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 16))

        # Loop Toggle
        tk.Checkbutton(
            ctrl_left,
            text="🔁 Loop Continuously",
            variable=self.loop_playback,
            font=("Inter", 9),
            fg=self.c_text,
            bg="#0d1835",
            selectcolor="#1e293b",
            activebackground="#0d1835"
        ).pack(side=tk.LEFT, padx=(0, 16))

        # Speed Multiplier
        tk.Label(ctrl_left, text="Speed:", font=("Inter", 9), fg=self.c_muted, bg="#0d1835").pack(side=tk.LEFT, padx=(0, 4))
        for spd in [0.5, 1.0, 1.5, 2.0]:
            btn = tk.Radiobutton(
                ctrl_left,
                text=f"{spd}x",
                variable=self.speed_multiplier,
                value=spd,
                font=("Inter", 8),
                fg=self.c_text,
                bg="#0d1835",
                selectcolor="#1e293b",
                activebackground="#0d1835"
            )
            btn.pack(side=tk.LEFT, padx=2)

        # Progress bar on the right
        right_box = tk.Frame(player, bg="#0d1835")
        right_box.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(20, 0))

        self.progress_lbl = tk.Label(right_box, text="Playback: Idle", font=("Inter", 8),
                                     fg=self.c_muted, bg="#0d1835")
        self.progress_lbl.pack(anchor="w", pady=(0, 2))

        self.prog_bar = ttk.Progressbar(right_box, orient=tk.HORIZONTAL, mode="determinate")
        self.prog_bar.pack(fill=tk.X)

    # --------------------------------------------------------------------------
    # 5. Bottom Status Bar
    # --------------------------------------------------------------------------
    def _build_bottom_bar(self):
        sbar = tk.Frame(self.root, bg="#070c1b", padx=16, pady=4)
        sbar.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_conn_lbl = tk.Label(sbar, text="🔴 Disconnected", font=("Inter", 8, "bold"),
                                        fg=self.c_red, bg="#070c1b")
        self.status_conn_lbl.pack(side=tk.LEFT)

        self.status_msg_lbl = tk.Label(sbar, text="Ready. Unlock torque to teach poses by hand, then press Space to capture.",
                                       font=("Inter", 8), fg=self.c_muted, bg="#070c1b")
        self.status_msg_lbl.pack(side=tk.LEFT, padx=12)

        tk.Label(sbar, text="Tip: Press Spacebar to quickly capture current pose",
                 font=("Inter", 8, "italic"), fg=self.c_cyan, bg="#070c1b").pack(side=tk.RIGHT)

    # --------------------------------------------------------------------------
    # Serial Communication Core
    # --------------------------------------------------------------------------
    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            for dev in ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"]:
                if os.path.exists(dev):
                    ports.append(dev)
        if not ports:
            ports = ["/dev/ttyUSB0"]

        self.port_combo["values"] = ports
        if "/dev/ttyUSB0" in ports:
            self.port_combo.set("/dev/ttyUSB0")
        elif ports:
            self.port_combo.set(ports[0])

    def _auto_connect_default(self):
        port = self.port_combo.get()
        if port and os.path.exists(port):
            self._connect_port(port, 115200)

    def _toggle_connection(self):
        if self.is_connected:
            self._disconnect_port()
        else:
            port = self.port_combo.get()
            self._connect_port(port, 115200)

    def _connect_port(self, port, baud):
        try:
            try:
                subprocess.run(f"fuser -k {port}", shell=True, capture_output=True)
            except Exception:
                pass
            time.sleep(0.15)

            self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.3)
            self.is_connected = True

            self.btn_connect.config(text="❌ Disconnect", bg=self.c_red)
            self.status_conn_lbl.config(text=f"🟢 Connected: {port}", fg=self.c_green)
            self.status_msg_lbl.config(text="Serial link active. Telemetry running.")

            # Start background poller
            self.stop_poller_event.clear()
            threading.Thread(target=self._telemetry_poll_loop, daemon=True).start()

        except Exception as e:
            self.is_connected = False
            messagebox.showerror("Connection Error", f"Could not connect to {port}:\n{e}")

    def _disconnect_port(self):
        self._stop_playback()
        self._stop_stream_recording()

        self.stop_poller_event.set()
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

        self.is_connected = False
        self.btn_connect.config(text="🔌 Connect", bg=self.c_green)
        self.status_conn_lbl.config(text="🔴 Disconnected", fg=self.c_red)
        self.status_msg_lbl.config(text="Serial port closed.")

    def _send_serial_cmd(self, cmd_dict: dict, wait_reply: bool = False, timeout: float = 0.5):
        if not self.is_connected or not self.ser or not self.ser.is_open:
            return None
        with self.serial_lock:
            try:
                msg = json.dumps(cmd_dict) + "\n"
                self.ser.write(msg.encode("utf-8"))

                if wait_reply:
                    start_t = time.time()
                    while time.time() - start_t < timeout:
                        line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                        if line.startswith("{") and line.endswith("}"):
                            try:
                                return json.loads(line)
                            except Exception:
                                pass
                return None
            except Exception as e:
                return None

    # --------------------------------------------------------------------------
    # Telemetry Polling Loop (Queries {"T": 5} continuously)
    # --------------------------------------------------------------------------
    def _telemetry_poll_loop(self):
        while not self.stop_poller_event.is_set():
            if self.is_connected and not self.is_playing:
                res = self._send_serial_cmd({"T": 5}, wait_reply=True, timeout=0.25)
                if res and "A1" in res:
                    self.current_angles[0] = float(res.get("A1", self.current_angles[0]))
                    self.current_angles[1] = float(res.get("A2", self.current_angles[1]))
                    self.current_angles[2] = float(res.get("A3", self.current_angles[2]))
                    self.current_angles[3] = float(res.get("A4", self.current_angles[3]))
                    self.current_angles[4] = float(res.get("A5", self.current_angles[4]))

                    self.root.after(0, self._update_telemetry_ui)
            time.sleep(0.12)

    def _update_telemetry_ui(self):
        for i in range(5):
            self.strip_labels[i].config(text=f"{self.current_angles[i]:.1f}°")
        self._draw_visualizer()

    # --------------------------------------------------------------------------
    # Hand-Teaching & Torque Operations
    # --------------------------------------------------------------------------
    def _set_torque(self, enable: bool):
        val = 1 if enable else 0
        self._send_serial_cmd({"T": 8, "P1": val})
        self.torque_enabled = enable

        if enable:
            self.lbl_torque_status.config(
                text="🔒 MOTORS LOCKED (Torque ON) — Arm holding position stiffly",
                fg=self.c_green
            )
            self.status_msg_lbl.config(text="Torque locked. Arm is holding position.")
        else:
            self.lbl_torque_status.config(
                text="🖐️ HAND-TEACH MODE (Torque OFF) — Gently pose the arm with your hands!",
                fg=self.c_amber
            )
            self.status_msg_lbl.config(text="Motors unlocked! Physically pose the arm, then press Spacebar.")

    def _home_robot(self):
        self._send_serial_cmd({"T": 11})
        self.current_angles = [180.0, 0.0, 90.0, 90.0, 180.0]
        self._update_telemetry_ui()
        self.status_msg_lbl.config(text="Arm returned to Home pose.")

    def _emergency_stop(self):
        self._stop_playback()
        self._stop_stream_recording()
        self._send_serial_cmd({"T": 0})
        self.torque_enabled = False
        self.lbl_torque_status.config(text="🛑 EMERGENCY STOPPED — Torque Released", fg=self.c_red)
        self.status_msg_lbl.config(text="Emergency stop sent! All motor power disabled.")

    # --------------------------------------------------------------------------
    # Waypoint Recording Methods
    # --------------------------------------------------------------------------
    def _capture_current_pose(self):
        # Query latest live angles
        res = self._send_serial_cmd({"T": 5}, wait_reply=True, timeout=0.3)
        if res and "A1" in res:
            angles = [
                round(float(res.get("A1", self.current_angles[0])), 1),
                round(float(res.get("A2", self.current_angles[1])), 1),
                round(float(res.get("A3", self.current_angles[2])), 1),
                round(float(res.get("A4", self.current_angles[3])), 1),
                round(float(res.get("A5", self.current_angles[4])), 1),
            ]
        else:
            angles = [round(a, 1) for a in self.current_angles]

        step_num = len(self.waypoints) + 1
        item = {
            "type": "pose",
            "angles": angles,
            "duration": 1.2,
            "delay": 0.3,
            "note": f"Waypoint {step_num}"
        }
        self.waypoints.append(item)
        self._refresh_table()

        # Select newly created row
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[-1])
            self.tree.see(children[-1])

        self.status_msg_lbl.config(text=f"Captured Waypoint #{step_num}: J1={angles[0]}° J2={angles[1]}° J3={angles[2]}° J4={angles[3]}° J5={angles[4]}°")

    def _add_delay_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Add Pause / Delay")
        win.geometry("300x150")
        win.configure(bg=self.c_card)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="Pause Duration (Seconds):", font=("Inter", 9, "bold"),
                 fg=self.c_text, bg=self.c_card).pack(pady=(16, 4))

        entry = tk.Entry(win, font=("JetBrains Mono", 11), bg=self.c_input, fg=self.c_cyan,
                         relief=tk.FLAT, insertbackground="#fff", justify="center")
        entry.insert(0, "1.0")
        entry.pack(pady=4, ipady=4)

        def confirm():
            try:
                sec = float(entry.get())
                self.waypoints.append({
                    "type": "delay",
                    "angles": list(self.current_angles),
                    "duration": sec,
                    "delay": sec,
                    "note": f"Pause {sec:.1f}s"
                })
                self._refresh_table()
                win.destroy()
            except ValueError:
                messagebox.showerror("Invalid Input", "Please enter a valid numeric duration.")

        tk.Button(win, text="Confirm", bg=self.c_blue, fg="#ffffff", font=("Inter", 9, "bold"),
                  relief=tk.FLAT, padx=12, pady=4, command=confirm).pack(pady=12)

    def _add_gripper_step(self, grip_angle: float, note: str):
        # Keeps current arm joints, sets gripper angle (180=open, 360=close)
        angles = list(self.current_angles)
        angles[4] = grip_angle
        self.waypoints.append({
            "type": "gripper",
            "angles": angles,
            "duration": 0.8,
            "delay": 0.2,
            "note": note
        })
        self._refresh_table()

    # --------------------------------------------------------------------------
    # Stream Recording (Fluid Continuous Motion Capture)
    # --------------------------------------------------------------------------
    def _toggle_stream_recording(self):
        if self.is_stream_recording:
            self._stop_stream_recording()
        else:
            self._start_stream_recording()

    def _start_stream_recording(self):
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to the robot first.")
            return

        self.is_stream_recording = True
        self.stop_stream_event.clear()
        self.btn_stream.config(text="⏹ Stop Stream", bg=self.c_red, fg="#ffffff")
        self._set_torque(False)
        self.status_msg_lbl.config(text="🔴 STREAM RECORDING ACTIVE: Move the arm smoothly by hand!")

        threading.Thread(target=self._stream_recording_loop, daemon=True).start()

    def _stop_stream_recording(self):
        self.is_stream_recording = False
        self.stop_stream_event.set()
        self.btn_stream.config(text="🔴 Stream Rec", bg="#450a0a", fg="#fca5a5")
        self.status_msg_lbl.config(text=f"Stream recording finished. Total waypoints: {len(self.waypoints)}")

    def _stream_recording_loop(self):
        last_recorded = None
        while not self.stop_stream_event.is_set():
            res = self._send_serial_cmd({"T": 5}, wait_reply=True, timeout=0.15)
            if res and "A1" in res:
                angles = [
                    round(float(res.get("A1", self.current_angles[0])), 1),
                    round(float(res.get("A2", self.current_angles[1])), 1),
                    round(float(res.get("A3", self.current_angles[2])), 1),
                    round(float(res.get("A4", self.current_angles[3])), 1),
                    round(float(res.get("A5", self.current_angles[4])), 1),
                ]

                # Filter tiny jitter
                if last_recorded is None or any(abs(angles[k] - last_recorded[k]) > 1.2 for k in range(5)):
                    item = {
                        "type": "pose",
                        "angles": angles,
                        "duration": 0.25,
                        "delay": 0.05,
                        "note": f"Stream pt {len(self.waypoints) + 1}"
                    }
                    self.waypoints.append(item)
                    last_recorded = angles
                    self.root.after(0, self._refresh_table)

            time.sleep(0.12)

    # --------------------------------------------------------------------------
    # Sequence Table Management & Editing
    # --------------------------------------------------------------------------
    def _refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        for i, item in enumerate(self.waypoints):
            tag = "even" if i % 2 == 0 else "odd"
            itype = item.get("type", "pose")
            type_display = {
                "pose": "📍 Pose",
                "delay": "⏱️ Delay",
                "gripper": "🦾 Gripper"
            }.get(itype, itype)

            ang = item.get("angles", [0, 0, 0, 0, 0])
            dur = f"{item.get('duration', 1.0):.1f}s"
            note = item.get("note", "")

            self.tree.insert("", tk.END, iid=str(i), values=(
                i + 1, type_display, f"{ang[0]:.1f}°", f"{ang[1]:.1f}°",
                f"{ang[2]:.1f}°", f"{ang[3]:.1f}°", f"{ang[4]:.1f}°", dur, note
            ), tags=(tag,))

        self.waypoint_count_lbl.config(text=f"{len(self.waypoints)} steps")

    def _on_waypoint_selected(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.waypoints):
            ghost = self.waypoints[idx].get("angles")
            self._draw_visualizer(ghost_angles=ghost)

    def _move_arm_to_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.waypoints):
            target = self.waypoints[idx]
            self._set_torque(True)
            self._execute_single_waypoint(target)

    def _update_selected_pose(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.waypoints):
            self.waypoints[idx]["angles"] = [round(a, 1) for a in self.current_angles]
            self._refresh_table()
            self.tree.selection_set(str(idx))
            self.status_msg_lbl.config(text=f"Updated step #{idx+1} with current live pose.")

    def _reorder_selected(self, direction: int):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        new_idx = idx + direction
        if 0 <= new_idx < len(self.waypoints):
            self.waypoints[idx], self.waypoints[new_idx] = self.waypoints[new_idx], self.waypoints[idx]
            self._refresh_table()
            self.tree.selection_set(str(new_idx))
            self.tree.see(str(new_idx))

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.waypoints):
            del self.waypoints[idx]
            self._refresh_table()

    def _clear_all_waypoints(self):
        if not self.waypoints:
            return
        if messagebox.askyesno("Clear Sequence", "Are you sure you want to delete all recorded waypoints?"):
            self.waypoints.clear()
            self._refresh_table()
            self._draw_visualizer()

    # --------------------------------------------------------------------------
    # Playback Engine
    # --------------------------------------------------------------------------
    def _start_playback(self):
        if self.is_playing:
            return
        if not self.waypoints:
            messagebox.showwarning("No Waypoints", "Sequence is empty! Capture some waypoints first.")
            return

        self._set_torque(True)
        self.is_playing = True
        self.is_paused = False
        self.stop_playback_event.clear()
        self.pause_playback_event.clear()

        self.btn_play.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.NORMAL)

        threading.Thread(target=self._playback_loop, daemon=True).start()

    def _toggle_pause_playback(self):
        if not self.is_playing:
            return
        if self.is_paused:
            self.is_paused = False
            self.pause_playback_event.clear()
            self.btn_pause.config(text="⏸️ Pause", bg="#1e293b")
            self.progress_lbl.config(text=f"Playing step #{self.current_playing_index + 1}...")
        else:
            self.is_paused = True
            self.pause_playback_event.set()
            self.btn_pause.config(text="▶️ Resume", bg=self.c_amber)
            self.progress_lbl.config(text="Playback Paused")

    def _stop_playback(self):
        self.is_playing = False
        self.is_paused = False
        self.stop_playback_event.set()
        self.pause_playback_event.clear()

        self.btn_play.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED, text="⏸️ Pause", bg="#1e293b")
        self.btn_stop.config(state=tk.DISABLED)
        self.prog_bar["value"] = 0
        self.progress_lbl.config(text="Playback: Stopped")

    def _playback_loop(self):
        while not self.stop_playback_event.is_set():
            total = len(self.waypoints)
            for i, step in enumerate(self.waypoints):
                if self.stop_playback_event.is_set():
                    break

                while self.pause_playback_event.is_set():
                    time.sleep(0.1)
                    if self.stop_playback_event.is_set():
                        break

                self.current_playing_index = i
                # Highlight in table
                self.root.after(0, self._highlight_playing_row, i, total)

                # Execute
                self._execute_single_waypoint(step)

            if not self.loop_playback.get():
                break

        self.root.after(0, self._stop_playback)

    def _highlight_playing_row(self, index, total):
        self.prog_bar["maximum"] = total
        self.prog_bar["value"] = index + 1
        self.progress_lbl.config(text=f"Executing step {index + 1} of {total}...")
        try:
            self.tree.selection_set(str(index))
            self.tree.see(str(index))
        except Exception:
            pass

    def _execute_single_waypoint(self, step):
        itype = step.get("type", "pose")
        mult = max(0.2, self.speed_multiplier.get())

        if itype == "delay":
            dur = step.get("duration", 1.0) / mult
            time.sleep(dur)
            return

        ang = step.get("angles", [180, 0, 90, 90, 180])
        spd = int(500 * mult)
        cmd = {
            "T": 1,
            "P1": round(ang[0], 2),
            "P2": max(-14.0, round(ang[1], 2)),
            "P3": round(ang[2], 2),
            "P4": round(ang[3], 2),
            "P5": round(ang[4], 2),
            "S1": spd, "S2": spd, "S3": spd, "S4": spd, "S5": spd,
            "A1": 60, "A2": 60, "A3": 60, "A4": 60, "A5": 60
        }
        self._send_serial_cmd(cmd)

        dur = step.get("duration", 1.0) / mult
        post_delay = step.get("delay", 0.2) / mult
        time.sleep(dur + post_delay)

    # --------------------------------------------------------------------------
    # File Storage: Save / Load Sequences
    # --------------------------------------------------------------------------
    def _save_routine_dialog(self):
        if not self.waypoints:
            messagebox.showwarning("Empty", "No waypoints to save.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("RoArm Routine (*.json)", "*.json")],
            title="Save RoArm Routine Sequence"
        )
        if path:
            try:
                data = {
                    "format": "RoArm-M1-Routine",
                    "version": 1.0,
                    "created": datetime.now().isoformat(),
                    "total_steps": len(self.waypoints),
                    "waypoints": self.waypoints
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                messagebox.showinfo("Saved", f"Successfully saved {len(self.waypoints)} waypoints to:\n{path}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Could not save file:\n{e}")

    def _load_routine_dialog(self):
        path = filedialog.askopenfilename(
            filetypes=[("RoArm Routine (*.json)", "*.json"), ("All files", "*.*")],
            title="Load RoArm Routine Sequence"
        )
        if path:
            self._load_routine_from_file(path)

    def _load_routine_from_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            wps = data.get("waypoints", [])
            if wps:
                self.waypoints = wps
                self._refresh_table()
                messagebox.showinfo("Loaded", f"Loaded {len(wps)} waypoints from:\n{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Load Error", f"Could not parse routine file:\n{e}")

    def _load_selected_preset(self):
        sel = self.preset_combo.get()
        if "Wave" in sel:
            self.waypoints = [
                {"type": "pose", "angles": [180, 0, 90, 90, 180], "duration": 1.0, "delay": 0.2, "note": "Home Pose"},
                {"type": "pose", "angles": [180, 30, 45, 90, 180], "duration": 1.2, "delay": 0.2, "note": "Salute Up"},
                {"type": "pose", "angles": [155, 30, 45, 90, 180], "duration": 0.6, "delay": 0.1, "note": "Wave Left"},
                {"type": "pose", "angles": [205, 30, 45, 90, 180], "duration": 0.6, "delay": 0.1, "note": "Wave Right"},
                {"type": "pose", "angles": [155, 30, 45, 90, 180], "duration": 0.6, "delay": 0.1, "note": "Wave Left"},
                {"type": "pose", "angles": [205, 30, 45, 90, 180], "duration": 0.6, "delay": 0.1, "note": "Wave Right"},
                {"type": "pose", "angles": [180, 0, 90, 90, 180], "duration": 1.0, "delay": 0.2, "note": "Return Home"}
            ]
        elif "Pick" in sel:
            self.waypoints = [
                {"type": "pose", "angles": [180, 0, 90, 90, 180], "duration": 1.0, "delay": 0.2, "note": "Home Ready"},
                {"type": "gripper", "angles": [180, 0, 90, 90, 180], "duration": 0.5, "delay": 0.2, "note": "Open Gripper"},
                {"type": "pose", "angles": [220, 25, 75, 45, 180], "duration": 1.2, "delay": 0.2, "note": "Hover Over Bin A"},
                {"type": "pose", "angles": [220, 45, 95, 20, 180], "duration": 0.8, "delay": 0.3, "note": "Descend to Object"},
                {"type": "gripper", "angles": [220, 45, 95, 20, 360], "duration": 0.6, "delay": 0.4, "note": "Grip Object"},
                {"type": "pose", "angles": [220, 10, 60, 50, 360], "duration": 1.0, "delay": 0.2, "note": "Lift Payload"},
                {"type": "pose", "angles": [140, 10, 60, 50, 360], "duration": 1.4, "delay": 0.2, "note": "Transfer to Bin B"},
                {"type": "pose", "angles": [140, 45, 95, 20, 360], "duration": 0.8, "delay": 0.3, "note": "Descend Target"},
                {"type": "gripper", "angles": [140, 45, 95, 20, 180], "duration": 0.6, "delay": 0.4, "note": "Release Object"},
                {"type": "pose", "angles": [180, 0, 90, 90, 180], "duration": 1.2, "delay": 0.2, "note": "Return to Home"}
            ]
        else:
            self.waypoints = [
                {"type": "pose", "angles": [180, 0, 90, 90, 180], "duration": 1.0, "delay": 0.2, "note": "Home"},
                {"type": "pose", "angles": [90, 15, 60, 90, 180], "duration": 1.5, "delay": 0.3, "note": "Scan Left 90°"},
                {"type": "pose", "angles": [270, 15, 60, 90, 180], "duration": 2.2, "delay": 0.3, "note": "Scan Right 270°"},
                {"type": "pose", "angles": [180, 0, 90, 90, 180], "duration": 1.2, "delay": 0.2, "note": "Return Home"}
            ]
        self._refresh_table()

    # --------------------------------------------------------------------------
    # Hardware ESP32 Flash Sync (T: 8)
    # --------------------------------------------------------------------------
    def _upload_to_esp32_flash(self):
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to serial port first.")
            return
        if not self.waypoints:
            messagebox.showwarning("Empty", "No waypoints to upload.")
            return

        # Clear NVS memory first
        self._send_serial_cmd({"T": 8, "P1": 777})
        time.sleep(0.3)

        pose_steps = [w for w in self.waypoints if w.get("type") in ("pose", "gripper")]
        self.status_msg_lbl.config(text=f"Uploading {len(pose_steps)} steps to ESP32 Flash...")

        def upload_thread():
            for idx, item in enumerate(pose_steps):
                ang = item.get("angles", [180, 0, 90, 90, 180])
                # Move to position
                cmd = {
                    "T": 1,
                    "P1": round(ang[0], 2), "P2": max(-14.0, round(ang[1], 2)),
                    "P3": round(ang[2], 2), "P4": round(ang[3], 2), "P5": round(ang[4], 2),
                    "S1": 800, "S2": 800, "S3": 800, "S4": 800, "S5": 800,
                    "A1": 60, "A2": 60, "A3": 60, "A4": 60, "A5": 60
                }
                self._send_serial_cmd(cmd)
                time.sleep(0.6)

                # Record into Flash step idx+1
                self._send_serial_cmd({"T": 8, "P1": 5, "P2": idx + 1, "P3": 5})
                time.sleep(0.3)

            self.root.after(0, lambda: messagebox.showinfo(
                "Upload Complete",
                f"Successfully saved {len(pose_steps)} steps directly into the robot's ESP32 Flash memory!"
            ))

        threading.Thread(target=upload_thread, daemon=True).start()

    def _trigger_hardware_replay(self):
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to serial port first.")
            return
        # T: 8, P1: 6, P2: 500 (step delay ms), P3: 1 (loop count)
        self._send_serial_cmd({"T": 8, "P1": 6, "P2": 500, "P3": 1})
        self.status_msg_lbl.config(text="Hardware replay triggered on robot onboard ESP32.")

    # --------------------------------------------------------------------------
    # Shutdown
    # --------------------------------------------------------------------------
    def _on_close(self):
        self._disconnect_port()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = RoArmRecordPlayGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
