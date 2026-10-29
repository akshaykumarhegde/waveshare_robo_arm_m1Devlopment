#!/usr/bin/env python3
"""
================================================================================
Waveshare RoArm-M1 Serial Command Studio / Console GUI
================================================================================
A dedicated, full-featured desktop GUI designed specifically for sending,
debugging, automating, and monitoring serial commands to the Waveshare RoArm-M1.

Features:
- Live Serial Port Selector with Auto-Detection & Busy Port (fuser) Release
- Real-time Bidirectional Console with Syntax Color-Coding (TX/RX/SYS/ERR)
- Timestamping, Auto-Scroll Lock, Real-Time Filter & Search
- Full RoArm-M1 JSON Command Preset Library (T:0 to T:13)
- Visual Command Builder (Generate and send T:1, T:2, T:3, T:5, T:8 with one click)
- Command History with Up/Down Arrow recall
- Multi-step Macro / Batch Script Runner with configurable delays
- Real-time Joint Angle & Servo Torque Telemetry Dashboard
- Log Exporter (Save to file)
================================================================================
"""

import sys
import os
import time
import json
import threading
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("Error: pyserial is required. Install with: pip install pyserial")
    sys.exit(1)


class RoArmSerialConsole:
    def __init__(self, root):
        self.root = root
        self.root.title("RoArm-M1 Serial Command Studio")
        self.root.geometry("1120x780")
        self.root.minsize(960, 640)

        # Color Theme (Modern Cyberpunk Slate / Dark Mode)
        self.c_bg = "#070b19"
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

        # Serial & Threading State
        self.ser = None
        self.is_connected = False
        self.rx_thread = None
        self.stop_rx_event = threading.Event()

        # Telemetry State
        self.polling_active = False
        self.polling_thread = None
        self.stop_polling_event = threading.Event()
        self.last_angles = [180.0, 0.0, 90.0, 90.0, 180.0]
        self.last_torques = [0, 0, 0, 0, 0]

        # Macro State
        self.macro_running = False
        self.stop_macro_event = threading.Event()

        # Command History
        self.cmd_history = []
        self.history_index = -1

        # Options
        self.show_timestamps = tk.BooleanVar(value=True)
        self.autoscroll = tk.BooleanVar(value=True)
        self.clear_on_send = tk.BooleanVar(value=False)
        self.append_newline = tk.StringVar(value="\\n")

        # Build UI
        self._setup_styles()
        self._build_top_bar()
        self._build_telemetry_bar()
        self._build_main_layout()
        self._build_bottom_bar()

        # Window Close Protocol
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Auto-detect and connect attempt
        self.root.after(400, self._auto_connect_default)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TCombobox",
                        fieldbackground=self.c_card,
                        background=self.c_card,
                        foreground=self.c_text)

        style.configure("TNotebook", background=self.c_card, borderwidth=0)
        style.configure("TNotebook.Tab", background="#1e293b", foreground=self.c_muted,
                        padding=[10, 5], font=("Inter", 9, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", self.c_blue)],
                  foreground=[("selected", "#ffffff")])

    # --------------------------------------------------------------------------
    # UI Header & Connection Panel
    # --------------------------------------------------------------------------
    def _build_top_bar(self):
        bar = tk.Frame(self.root, bg="#0d1835", padx=16, pady=10)
        bar.pack(fill=tk.X, side=tk.TOP)

        # Brand / Title
        left = tk.Frame(bar, bg="#0d1835")
        left.pack(side=tk.LEFT)

        tk.Label(left, text="⚡", font=("Segoe UI Emoji", 20), bg="#0d1835").pack(side=tk.LEFT, padx=(0, 8))
        title_box = tk.Frame(left, bg="#0d1835")
        title_box.pack(side=tk.LEFT)
        tk.Label(title_box, text="RoArm-M1 Serial Command Studio",
                 font=("Inter", 13, "bold"), fg=self.c_text, bg="#0d1835").pack(anchor="w")
        tk.Label(title_box, text="Interactive JSON & Raw Protocol Dispatcher",
                 font=("Inter", 8), fg=self.c_muted, bg="#0d1835").pack(anchor="w")

        # Connection Controls
        right = tk.Frame(bar, bg="#0d1835")
        right.pack(side=tk.RIGHT)

        tk.Label(right, text="Port:", font=("Inter", 9), fg=self.c_muted, bg="#0d1835").pack(side=tk.LEFT, padx=(6, 2))
        self.port_combo = ttk.Combobox(right, width=15, state="readonly")
        self.port_combo.pack(side=tk.LEFT, padx=2)
        self._refresh_ports()

        btn_refresh = tk.Button(right, text="🔄", bg="#1e293b", fg=self.c_text, relief=tk.FLAT,
                                font=("Segoe UI Emoji", 9), command=self._refresh_ports)
        btn_refresh.pack(side=tk.LEFT, padx=(2, 8))

        tk.Label(right, text="Baud:", font=("Inter", 9), fg=self.c_muted, bg="#0d1835").pack(side=tk.LEFT, padx=(4, 2))
        self.baud_combo = ttk.Combobox(right, width=8, state="readonly",
                                       values=["9600", "57600", "115200", "230400", "921600"])
        self.baud_combo.set("115200")
        self.baud_combo.pack(side=tk.LEFT, padx=2)

        self.btn_connect = tk.Button(right, text="🔌 Connect", bg=self.c_green, fg="#ffffff",
                                     font=("Inter", 9, "bold"), relief=tk.FLAT, padx=12, pady=4,
                                     cursor="hand2", command=self._toggle_connection)
        self.btn_connect.pack(side=tk.LEFT, padx=(8, 4))

        btn_fuser = tk.Button(right, text="Free Port", bg="#334155", fg=self.c_muted,
                              font=("Inter", 8), relief=tk.FLAT, padx=6, pady=4,
                              command=self._release_port_dialog)
        btn_fuser.pack(side=tk.LEFT, padx=(2, 0))

    # --------------------------------------------------------------------------
    # Telemetry Status Cards Bar
    # --------------------------------------------------------------------------
    def _build_telemetry_bar(self):
        tbar = tk.Frame(self.root, bg="#0b1329", padx=16, pady=6)
        tbar.pack(fill=tk.X, side=tk.TOP)

        self.telemetry_labels = []
        joint_names = ["J1 (Base)", "J2 (Shoulder)", "J3 (Elbow)", "J4 (Wrist)", "J5 (Grip)"]

        for i, name in enumerate(joint_names):
            card = tk.Frame(tbar, bg="#0f172a", highlightthickness=1,
                            highlightbackground=self.c_card_border, padx=10, pady=4)
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)

            tk.Label(card, text=name, font=("Inter", 8), fg=self.c_muted, bg="#0f172a").pack(anchor="w")
            val_lbl = tk.Label(card, text="--°", font=("JetBrains Mono", 10, "bold"),
                               fg=self.c_cyan, bg="#0f172a")
            val_lbl.pack(anchor="w")
            self.telemetry_labels.append(val_lbl)

        # Right-side Auto-poll toggle
        poll_box = tk.Frame(tbar, bg="#0b1329")
        poll_box.pack(side=tk.RIGHT, padx=4)

        self.poll_var = tk.BooleanVar(value=False)
        self.poll_check = tk.Checkbutton(poll_box, text="Auto-Poll (T:5)", variable=self.poll_var,
                                         font=("Inter", 9), fg=self.c_text, bg="#0b1329",
                                         selectcolor="#1e293b", activebackground="#0b1329",
                                         command=self._toggle_polling)
        self.poll_check.pack(side=tk.LEFT)

    # --------------------------------------------------------------------------
    # Main Content Area: Left (Presets & Builder) | Right (Terminal)
    # --------------------------------------------------------------------------
    def _build_main_layout(self):
        container = tk.Frame(self.root, bg=self.c_bg, padx=16, pady=8)
        container.pack(fill=tk.BOTH, expand=True)

        # Left Column (Presets, Interactive Builder, Script Macro)
        left_col = tk.Frame(container, bg=self.c_card, highlightbackground=self.c_card_border,
                            highlightthickness=1, width=420)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 8))
        left_col.pack_propagate(False)

        # Right Column (Terminal Console, Filters, Single/Multi Dispatcher)
        right_col = tk.Frame(container, bg=self.c_card, highlightbackground=self.c_card_border,
                             highlightthickness=1)
        right_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_left_toolbox(left_col)
        self._build_right_terminal(right_col)

    # --------------------------------------------------------------------------
    # Left Toolbox: Tabs for Presets, Builder, Macro Scripts
    # --------------------------------------------------------------------------
    def _build_left_toolbox(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        tab_presets = tk.Frame(nb, bg=self.c_card)
        tab_builder = tk.Frame(nb, bg=self.c_card)
        tab_macro = tk.Frame(nb, bg=self.c_card)

        nb.add(tab_presets, text="📋 Quick Presets")
        nb.add(tab_builder, text="🛠️ JSON Builder")
        nb.add(tab_macro, text="📜 Macro Runner")

        self._populate_presets_tab(tab_presets)
        self._populate_builder_tab(tab_builder)
        self._populate_macro_tab(tab_macro)

    def _populate_presets_tab(self, parent):
        canvas = tk.Canvas(parent, bg=self.c_card, highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=self.c_card)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=390)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def add_header(txt, col):
            tk.Label(scroll_frame, text=txt, font=("Inter", 9, "bold"),
                     fg=col, bg=self.c_card).pack(anchor="w", pady=(10, 4), padx=6)

        def add_btn(txt, cmd_str, bg="#1e293b", fg=self.c_text):
            btn = tk.Button(scroll_frame, text=txt, font=("Inter", 8, "bold"), bg=bg, fg=fg,
                            relief=tk.FLAT, anchor="w", padx=8, pady=4, cursor="hand2",
                            command=lambda c=cmd_str: self.send_command_raw(c))
            btn.pack(fill=tk.X, padx=6, pady=2)

        # 1. Emergency & System Initializations
        add_header("🚨 SYSTEM & INITIALIZATION", self.c_red)
        add_btn("🛑 Emergency Stop: {\"T\": 0}", '{"T": 0}', bg="#7f1d1d", fg="#fecaca")
        add_btn("🏠 Angle Init (Home All): {\"T\": 11}", '{"T": 11}', bg="#065f46", fg="#a7f3d0")
        add_btn("📐 Cartesian Init (277, -13, 276): {\"T\": 12}", '{"T": 12}', bg="#1e3a8a", fg="#bfdbfe")
        add_btn("🔄 Raw Servo Middle Init (2047): {\"T\": 13}", '{"T": 13}')
        add_btn("🔓 Torque OFF (Hand-Teach): {\"T\": 8, \"P1\": 0}", '{"T": 8, "P1": 0}', bg="#78350f", fg="#fde68a")
        add_btn("🔒 Torque ON (Hold Pose): {\"T\": 8, \"P1\": 1}", '{"T": 8, "P1": 1}')

        # 2. Diagnostics & Telemetry
        add_header("📊 FEEDBACK & QUERIES", self.c_cyan)
        add_btn("📡 Get Angle & Torque Info: {\"T\": 5}", '{"T": 5}', bg="#164e63", fg="#a5f3fc")
        add_btn("ℹ️ Get Device Info: {\"T\": 4}", '{"T": 4}')
        add_btn("🧮 Get Kinematics Buffer: {\"T\": 6}", '{"T": 6}')
        add_btn("❓ Get Help Manual: {\"T\": 10}", '{"T": 10}')

        # 3. Gripper Quick Moves
        add_header("🦾 GRIPPER COMMANDS", self.c_amber)
        add_btn("🔓 Fully Open Gripper (P5: 180°)",
                '{"T":1,"P1":180,"P2":0,"P3":90,"P4":90,"P5":180,"S1":500,"S2":500,"S3":500,"S4":500,"S5":500,"A1":60,"A2":60,"A3":60,"A4":60,"A5":60}')
        add_btn("🔒 Fully Close Gripper (P5: 360°)",
                '{"T":1,"P1":180,"P2":0,"P3":90,"P4":90,"P5":360,"S1":500,"S2":500,"S3":500,"S4":500,"S5":500,"A1":60,"A2":60,"A3":60,"A4":60,"A5":60}')
        add_btn("🤏 Half Grip (P5: 270°)",
                '{"T":1,"P1":180,"P2":0,"P3":90,"P4":90,"P5":270,"S1":500,"S2":500,"S3":500,"S4":500,"S5":500,"A1":60,"A2":60,"A3":60,"A4":60,"A5":60}')

        # 4. Wrist Pitch Adjustments (0° = Level, 90° = Straight Down)
        add_header("📐 WRIST PITCH QUICK ANGLES", self.c_purple)
        add_btn("⬆️ Wrist Pitch Up (-20° | P4: -20°)",
                '{"T":1,"P1":180,"P2":0,"P3":90,"P4":-20,"P5":180,"S1":500,"S2":500,"S3":500,"S4":500,"S5":500,"A1":60,"A2":60,"A3":60,"A4":60,"A5":60}')
        add_btn("➡️ Wrist Pitch Straight Level (0° | P4: 0°)",
                '{"T":1,"P1":180,"P2":0,"P3":90,"P4":0,"P5":180,"S1":500,"S2":500,"S3":500,"S4":500,"S5":500,"A1":60,"A2":60,"A3":60,"A4":60,"A5":60}')
        add_btn("↘️ Wrist Pitch Down 45° (+45° | P4: 45°)",
                '{"T":1,"P1":180,"P2":0,"P3":90,"P4":45,"P5":180,"S1":500,"S2":500,"S3":500,"S4":500,"S5":500,"A1":60,"A2":60,"A3":60,"A4":60,"A5":60}')
        add_btn("⬇️ Wrist Pitch Straight Down (+90° | P4: 90°)",
                '{"T":1,"P1":180,"P2":0,"P3":90,"P4":90,"P5":180,"S1":500,"S2":500,"S3":500,"S4":500,"S5":500,"A1":60,"A2":60,"A3":60,"A4":60,"A5":60}')

    def _populate_builder_tab(self, parent):
        frame = tk.Frame(parent, bg=self.c_card, padx=10, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="Command Type:", font=("Inter", 9, "bold"),
                 fg=self.c_muted, bg=self.c_card).pack(anchor="w")

        types = [
            "T: 1 (Joint Angles)",
            "T: 2 (Cartesian Coordinate)",
            "T: 3 (Raw Servo Steps)",
            "T: 8 (Torque / Replay)"
        ]
        self.builder_type_var = tk.StringVar(value=types[0])
        self.builder_type_combo = ttk.Combobox(frame, textvariable=self.builder_type_var,
                                               values=types, state="readonly")
        self.builder_type_combo.pack(fill=tk.X, pady=(2, 8))
        self.builder_type_combo.bind("<<ComboboxSelected>>", self._on_builder_type_change)

        # Fields Grid Container
        self.builder_fields_frame = tk.Frame(frame, bg=self.c_card)
        self.builder_fields_frame.pack(fill=tk.X, pady=4)
        self.builder_entries = {}

        # Live JSON Preview Box
        tk.Label(frame, text="Generated JSON Preview:", font=("Inter", 9, "bold"),
                 fg=self.c_cyan, bg=self.c_card).pack(anchor="w", pady=(10, 2))

        self.builder_preview = tk.Text(frame, height=4, bg=self.c_input, fg=self.c_text,
                                       font=("JetBrains Mono", 8), relief=tk.FLAT)
        self.builder_preview.pack(fill=tk.X, pady=2)

        self._render_builder_fields("T: 1 (Joint Angles)")

        # Buttons
        btn_box = tk.Frame(frame, bg=self.c_card)
        btn_box.pack(fill=tk.X, pady=(8, 0))

        tk.Button(btn_box, text="⚡ Send Built Command", bg=self.c_blue, fg="#ffffff",
                  font=("Inter", 9, "bold"), relief=tk.FLAT, pady=5, cursor="hand2",
                  command=self._send_built_cmd).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        tk.Button(btn_box, text="📋 Insert to Input", bg="#334155", fg="#ffffff",
                  font=("Inter", 9), relief=tk.FLAT, pady=5,
                  command=self._insert_built_to_input).pack(side=tk.LEFT, padx=(4, 0))

    def _render_builder_fields(self, t_type):
        for widget in self.builder_fields_frame.winfo_children():
            widget.destroy()
        self.builder_entries.clear()

        if "T: 1" in t_type:
            labels = [
                ("P1 (Base Pan °)", "180"),
                ("P2 (Shoulder ° [-90 to 90])", "0"),
                ("P3 (Elbow °)", "90"),
                ("P4 (Wrist Pitch ° [0-180])", "90"),
                ("P5 (Gripper ° [180=Open, 360=Close])", "180"),
                ("S (Speed steps/s)", "500"),
                ("A (Acceleration)", "60")
            ]
        elif "T: 2" in t_type:
            labels = [
                ("P1 (X mm)", "277.5"),
                ("P2 (Y mm)", "-13.8"),
                ("P3 (Z mm)", "276.6"),
                ("P4 (Theta °)", "90.0"),
                ("P5 (Gripper °)", "180"),
                ("S1 (Step Delay ms)", "10"),
                ("S5 (Gripper Speed)", "200")
            ]
        elif "T: 3" in t_type:
            labels = [
                ("P1 (Step 0-4095)", "2047"),
                ("P2 (Step 0-4095)", "2047"),
                ("P3 (Step 0-4095)", "2047"),
                ("P4 (Step 0-4095)", "2047"),
                ("P5 (Step 0-4095)", "2047"),
                ("S (Speed)", "500"),
                ("A (Acc)", "60")
            ]
        else:
            labels = [
                ("P1 (0=Torque OFF, 1=Torque ON)", "1"),
                ("P2 (Sub-param / Step)", "0"),
                ("P3 (Param)", "0")
            ]

        for i, (name, val) in enumerate(labels):
            row = tk.Frame(self.builder_fields_frame, bg=self.c_card)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=name, font=("Inter", 8), fg=self.c_muted, bg=self.c_card).pack(side=tk.LEFT)
            entry = tk.Entry(row, font=("JetBrains Mono", 8), bg=self.c_input, fg=self.c_text,
                             relief=tk.FLAT, insertbackground="#fff", width=12)
            entry.insert(0, val)
            entry.pack(side=tk.RIGHT)
            entry.bind("<KeyRelease>", lambda e: self._update_builder_preview())
            self.builder_entries[name.split()[0]] = entry

        self._update_builder_preview()

    def _on_builder_type_change(self, event=None):
        self._render_builder_fields(self.builder_type_var.get())

    def _update_builder_preview(self):
        cmd = self._generate_built_json()
        self.builder_preview.delete("1.0", tk.END)
        self.builder_preview.insert(tk.END, json.dumps(cmd))

    def _generate_built_json(self):
        t_sel = self.builder_type_var.get()
        if "T: 1" in t_sel:
            p1 = float(self.builder_entries.get("P1", tk.Entry()).get() or 180)
            p2 = float(self.builder_entries.get("P2", tk.Entry()).get() or 0)
            p3 = float(self.builder_entries.get("P3", tk.Entry()).get() or 90)
            p4 = float(self.builder_entries.get("P4", tk.Entry()).get() or 90)
            p5 = float(self.builder_entries.get("P5", tk.Entry()).get() or 180)
            spd = int(self.builder_entries.get("S", tk.Entry()).get() or 500)
            acc = int(self.builder_entries.get("A", tk.Entry()).get() or 60)
            return {
                "T": 1, "P1": p1, "P2": p2, "P3": p3, "P4": p4, "P5": p5,
                "S1": spd, "S2": spd, "S3": spd, "S4": spd, "S5": spd,
                "A1": acc, "A2": acc, "A3": acc, "A4": acc, "A5": acc
            }
        elif "T: 2" in t_sel:
            x = float(self.builder_entries.get("P1", tk.Entry()).get() or 277.5)
            y = float(self.builder_entries.get("P2", tk.Entry()).get() or -13.8)
            z = float(self.builder_entries.get("P3", tk.Entry()).get() or 276.6)
            theta = float(self.builder_entries.get("P4", tk.Entry()).get() or 90.0)
            p5 = float(self.builder_entries.get("P5", tk.Entry()).get() or 180)
            s1 = int(self.builder_entries.get("S1", tk.Entry()).get() or 10)
            s5 = int(self.builder_entries.get("S5", tk.Entry()).get() or 200)
            return {"T": 2, "P1": x, "P2": y, "P3": z, "P4": theta, "P5": p5, "S1": s1, "S5": s5}
        elif "T: 3" in t_sel:
            p1 = int(self.builder_entries.get("P1", tk.Entry()).get() or 2047)
            p2 = int(self.builder_entries.get("P2", tk.Entry()).get() or 2047)
            p3 = int(self.builder_entries.get("P3", tk.Entry()).get() or 2047)
            p4 = int(self.builder_entries.get("P4", tk.Entry()).get() or 2047)
            p5 = int(self.builder_entries.get("P5", tk.Entry()).get() or 2047)
            spd = int(self.builder_entries.get("S", tk.Entry()).get() or 500)
            acc = int(self.builder_entries.get("A", tk.Entry()).get() or 60)
            return {
                "T": 3, "P1": p1, "P2": p2, "P3": p3, "P4": p4, "P5": p5,
                "S1": spd, "S2": spd, "S3": spd, "S4": spd, "S5": spd,
                "A1": acc, "A2": acc, "A3": acc, "A4": acc, "A5": acc
            }
        else:
            p1 = int(self.builder_entries.get("P1", tk.Entry()).get() or 1)
            p2 = int(self.builder_entries.get("P2", tk.Entry()).get() or 0)
            p3 = int(self.builder_entries.get("P3", tk.Entry()).get() or 0)
            return {"T": 8, "P1": p1, "P2": p2, "P3": p3}

    def _send_built_cmd(self):
        cmd = self._generate_built_json()
        self.send_command_raw(json.dumps(cmd))

    def _insert_built_to_input(self):
        cmd = self._generate_built_json()
        self.cmd_input.delete(0, tk.END)
        self.cmd_input.insert(0, json.dumps(cmd))

    def _populate_macro_tab(self, parent):
        frame = tk.Frame(parent, bg=self.c_card, padx=10, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="Multi-step Sequence Script:", font=("Inter", 9, "bold"),
                 fg=self.c_text, bg=self.c_card).pack(anchor="w")
        tk.Label(frame, text="Write JSON commands or '# delay <seconds>'",
                 font=("Inter", 8), fg=self.c_muted, bg=self.c_card).pack(anchor="w", pady=(0, 4))

        self.macro_text = tk.Text(frame, bg=self.c_input, fg="#38bdf8", font=("JetBrains Mono", 8),
                                  relief=tk.FLAT, insertbackground="#fff", height=14)
        self.macro_text.pack(fill=tk.BOTH, expand=True, pady=4)

        # Default Example Sequence
        default_macro = (
            "# RoArm-M1 Demonstration Sequence\n"
            '{"T": 11}\n'
            "# delay 1.5\n"
            '{"T": 1, "P1": 180, "P2": 0, "P3": 90, "P4": 110, "P5": 180, "S1": 500, "S2": 500, "S3": 500, "S4": 500, "S5": 500, "A1": 60, "A2": 60, "A3": 60, "A4": 60, "A5": 60}\n'
            "# delay 1.0\n"
            '{"T": 1, "P1": 180, "P2": 0, "P3": 90, "P4": 45, "P5": 90, "S1": 500, "S2": 500, "S3": 500, "S4": 500, "S5": 500, "A1": 60, "A2": 60, "A3": 60, "A4": 60, "A5": 60}\n'
            "# delay 1.0\n"
            '{"T": 11}\n'
        )
        self.macro_text.insert(tk.END, default_macro)

        btn_row = tk.Frame(frame, bg=self.c_card)
        btn_row.pack(fill=tk.X, pady=(6, 0))

        self.btn_run_macro = tk.Button(btn_row, text="▶ Run Macro", bg=self.c_green, fg="#ffffff",
                                       font=("Inter", 9, "bold"), relief=tk.FLAT, pady=4, cursor="hand2",
                                       command=self._start_macro)
        self.btn_run_macro.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.btn_stop_macro = tk.Button(btn_row, text="⏹ Stop", bg=self.c_red, fg="#ffffff",
                                        font=("Inter", 9, "bold"), relief=tk.FLAT, pady=4, state=tk.DISABLED,
                                        command=self._stop_macro)
        self.btn_stop_macro.pack(side=tk.LEFT, padx=(4, 0))

    # --------------------------------------------------------------------------
    # Right Column: High-Performance Bidirectional Protocol Terminal
    # --------------------------------------------------------------------------
    def _build_right_terminal(self, parent):
        # Console Options & Search Header
        ctrl_bar = tk.Frame(parent, bg=self.c_card, padx=10, pady=8)
        ctrl_bar.pack(fill=tk.X)

        tk.Label(ctrl_bar, text="Console Stream:", font=("Inter", 10, "bold"),
                 fg=self.c_cyan, bg=self.c_card).pack(side=tk.LEFT, padx=(0, 10))

        tk.Checkbutton(ctrl_bar, text="Timestamps", variable=self.show_timestamps,
                       font=("Inter", 8), fg=self.c_muted, bg=self.c_card,
                       selectcolor="#1e293b", activebackground=self.c_card).pack(side=tk.LEFT, padx=4)

        tk.Checkbutton(ctrl_bar, text="Auto-scroll", variable=self.autoscroll,
                       font=("Inter", 8), fg=self.c_muted, bg=self.c_card,
                       selectcolor="#1e293b", activebackground=self.c_card).pack(side=tk.LEFT, padx=4)

        tk.Button(ctrl_bar, text="🗑️ Clear", bg="#1e293b", fg=self.c_text, font=("Inter", 8),
                  relief=tk.FLAT, padx=6, pady=2, command=self._clear_console).pack(side=tk.RIGHT, padx=4)

        tk.Button(ctrl_bar, text="💾 Save Log", bg="#1e293b", fg=self.c_text, font=("Inter", 8),
                  relief=tk.FLAT, padx=6, pady=2, command=self._save_log_dialog).pack(side=tk.RIGHT, padx=4)

        # Real-time search/filter
        tk.Label(ctrl_bar, text="Filter:", font=("Inter", 8), fg=self.c_muted, bg=self.c_card).pack(side=tk.RIGHT, padx=(8, 2))
        self.filter_entry = tk.Entry(ctrl_bar, font=("Inter", 8), bg=self.c_input, fg=self.c_text,
                                     relief=tk.FLAT, insertbackground="#fff", width=12)
        self.filter_entry.pack(side=tk.RIGHT)

        # Main Log Text Area
        log_box = tk.Frame(parent, bg=self.c_card, padx=10, pady=4)
        log_box.pack(fill=tk.BOTH, expand=True)

        self.terminal = tk.Text(log_box, bg="#030712", fg="#e2e8f0", font=("JetBrains Mono", 9),
                                relief=tk.FLAT, wrap=tk.CHAR)
        self.terminal.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(log_box, command=self.terminal.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.terminal.config(yscrollcommand=scrollbar.set)

        # Tag Styles for Color-Coding
        self.terminal.tag_config("tx", foreground="#10b981")       # Sent: Bright green
        self.terminal.tag_config("rx", foreground="#38bdf8")       # Received: Bright cyan
        self.terminal.tag_config("sys", foreground="#f59e0b")      # System: Amber
        self.terminal.tag_config("err", foreground="#ef4444")      # Error: Red
        self.terminal.tag_config("dim", foreground="#64748b")      # Dim/Timestamp: Muted

        # Command Dispatcher Input Area (Bottom of Right Column)
        input_panel = tk.Frame(parent, bg="#0d1835", padx=10, pady=10)
        input_panel.pack(fill=tk.X, side=tk.BOTTOM)

        top_in = tk.Frame(input_panel, bg="#0d1835")
        top_in.pack(fill=tk.X, pady=(0, 4))

        tk.Label(top_in, text="Prompt / Command Dispatcher:", font=("Inter", 8, "bold"),
                 fg=self.c_muted, bg="#0d1835").pack(side=tk.LEFT)

        tk.Checkbutton(top_in, text="Clear on send", variable=self.clear_on_send,
                       font=("Inter", 8), fg=self.c_muted, bg="#0d1835",
                       selectcolor="#1e293b", activebackground="#0d1835").pack(side=tk.RIGHT, padx=4)

        tk.Label(top_in, text="Ending:", font=("Inter", 8), fg=self.c_muted, bg="#0d1835").pack(side=tk.RIGHT, padx=(4, 2))
        combo_end = ttk.Combobox(top_in, textvariable=self.append_newline, width=6, state="readonly",
                                 values=["\\n", "\\r\\n", "None"])
        combo_end.pack(side=tk.RIGHT)

        row_in = tk.Frame(input_panel, bg="#0d1835")
        row_in.pack(fill=tk.X)

        self.cmd_input = tk.Entry(row_in, font=("JetBrains Mono", 10), bg="#030712", fg="#38bdf8",
                                  relief=tk.FLAT, insertbackground="#38bdf8")
        self.cmd_input.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 8))
        self.cmd_input.bind("<Return>", lambda e: self._on_send_pressed())
        self.cmd_input.bind("<Up>", self._history_up)
        self.cmd_input.bind("<Down>", self._history_down)

        self.btn_send = tk.Button(row_in, text="🚀 Send", bg=self.c_blue, fg="#ffffff",
                                  font=("Inter", 10, "bold"), relief=tk.FLAT, padx=16, pady=4,
                                  cursor="hand2", command=self._on_send_pressed)
        self.btn_send.pack(side=tk.RIGHT)

    # --------------------------------------------------------------------------
    # Bottom Status Bar
    # --------------------------------------------------------------------------
    def _build_bottom_bar(self):
        sbar = tk.Frame(self.root, bg="#0b1329", padx=16, pady=4)
        sbar.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_conn_lbl = tk.Label(sbar, text="🔴 Disconnected", font=("Inter", 8, "bold"),
                                        fg=self.c_red, bg="#0b1329")
        self.status_conn_lbl.pack(side=tk.LEFT)

        self.status_msg_lbl = tk.Label(sbar, text="Ready. Select serial port and click Connect.",
                                       font=("Inter", 8), fg=self.c_muted, bg="#0b1329")
        self.status_msg_lbl.pack(side=tk.LEFT, padx=12)

        self.status_counters_lbl = tk.Label(sbar, text="TX: 0 B | RX: 0 B", font=("JetBrains Mono", 8),
                                            fg=self.c_muted, bg="#0b1329")
        self.status_counters_lbl.pack(side=tk.RIGHT)

        self.bytes_tx = 0
        self.bytes_rx = 0

    # --------------------------------------------------------------------------
    # Serial Port Management
    # --------------------------------------------------------------------------
    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            # Fallback for linux USB devices
            for dev in ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"]:
                if os.path.exists(dev):
                    ports.append(dev)
        if not ports:
            ports = ["/dev/ttyUSB0"]

        self.port_combo["values"] = ports
        if ports:
            if "/dev/ttyUSB0" in ports:
                self.port_combo.set("/dev/ttyUSB0")
            else:
                self.port_combo.set(ports[0])

    def _auto_connect_default(self):
        port = self.port_combo.get()
        if port and os.path.exists(port):
            self._connect_port(port, 115200)

    def _release_port_dialog(self):
        port = self.port_combo.get()
        if not port:
            return
        try:
            cmd = f"fuser -k {port}"
            subprocess.run(cmd, shell=True, capture_output=True)
            self._log_terminal(f"SYS: Released lock on {port} with fuser -k", "sys")
            time.sleep(0.3)
        except Exception as e:
            self._log_terminal(f"ERR: Failed to release port: {e}", "err")

    def _toggle_connection(self):
        if self.is_connected:
            self._disconnect_port()
        else:
            port = self.port_combo.get()
            baud = int(self.baud_combo.get() or 115200)
            self._connect_port(port, baud)

    def _connect_port(self, port, baud):
        try:
            # First release any stale lock
            try:
                subprocess.run(f"fuser -k {port}", shell=True, capture_output=True)
            except Exception:
                pass
            time.sleep(0.15)

            self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.1)
            self.is_connected = True

            self.btn_connect.config(text="❌ Disconnect", bg=self.c_red)
            self.status_conn_lbl.config(text=f"🟢 Connected: {port} @ {baud}", fg=self.c_green)
            self.status_msg_lbl.config(text="Serial link active and receiving telemetry.")

            self._log_terminal(f"SYS: Connected to {port} @ {baud} baud.", "sys")

            # Start RX background thread
            self.stop_rx_event.clear()
            self.rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
            self.rx_thread.start()

        except Exception as e:
            self.is_connected = False
            self._log_terminal(f"ERR: Failed to open {port}: {e}", "err")
            messagebox.showerror("Connection Failed", f"Could not open {port}:\n{e}")

    def _disconnect_port(self):
        self._stop_macro()
        self._stop_polling()

        self.stop_rx_event.set()
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

        self.is_connected = False
        self.btn_connect.config(text="🔌 Connect", bg=self.c_green)
        self.status_conn_lbl.config(text="🔴 Disconnected", fg=self.c_red)
        self.status_msg_lbl.config(text="Connection closed.")
        self._log_terminal("SYS: Port disconnected.", "sys")

    # --------------------------------------------------------------------------
    # Background RX Thread & Protocol Parser
    # --------------------------------------------------------------------------
    def _rx_loop(self):
        buffer = bytearray()
        while not self.stop_rx_event.is_set() and self.ser and self.ser.is_open:
            try:
                waiting = self.ser.in_waiting
                if waiting > 0:
                    chunk = self.ser.read(waiting)
                    self.bytes_rx += len(chunk)
                    buffer.extend(chunk)

                    while b"\n" in buffer:
                        idx = buffer.index(b"\n")
                        line_bytes = buffer[:idx]
                        del buffer[:idx + 1]

                        line_str = line_bytes.decode("utf-8", errors="replace").strip("\r ")
                        if line_str:
                            self.root.after(0, self._handle_rx_line, line_str)
                else:
                    time.sleep(0.01)
            except Exception as e:
                if not self.stop_rx_event.is_set():
                    self.root.after(0, self._log_terminal, f"ERR: Serial read error: {e}", "err")
                break

    def _handle_rx_line(self, line):
        # Update byte counter
        self.status_counters_lbl.config(text=f"TX: {self.bytes_tx} B | RX: {self.bytes_rx} B")

        # Check filter
        filt = self.filter_entry.get().strip()
        if filt and filt.lower() not in line.lower():
            return

        # Attempt to parse as JSON telemetry to update cards
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                # T:5 Angle & Torque Info
                if "A1" in data:
                    self._update_telemetry_cards(data)
                # T:1 Echo
                elif "P1" in data and "T" in data and data.get("T") == 1:
                    self._update_echo_cards(data)
            except Exception:
                pass

        self._log_terminal(f"RX << {line}", "rx")

    def _update_telemetry_cards(self, data):
        for i in range(5):
            k_a = f"A{i+1}"
            k_t = f"T{i+1}"
            if k_a in data:
                ang = float(data[k_a])
                load = int(data.get(k_t, 0))
                self.last_angles[i] = ang
                self.last_torques[i] = load
                self.telemetry_labels[i].config(
                    text=f"{ang:.1f}° ({load})",
                    fg=self.c_green if abs(load) < 150 else self.c_amber
                )

    def _update_echo_cards(self, data):
        for i in range(5):
            k_p = f"P{i+1}"
            if k_p in data:
                ang = float(data[k_p])
                self.last_angles[i] = ang
                self.telemetry_labels[i].config(text=f"{ang:.1f}°")

    # --------------------------------------------------------------------------
    # Command Sending & Terminal Dispatcher
    # --------------------------------------------------------------------------
    def _on_send_pressed(self):
        text = self.cmd_input.get().strip()
        if not text:
            return

        # History tracking
        if not self.cmd_history or self.cmd_history[-1] != text:
            self.cmd_history.append(text)
        self.history_index = len(self.cmd_history)

        self.send_command_raw(text)

        if self.clear_on_send.get():
            self.cmd_input.delete(0, tk.END)

    def send_command_raw(self, cmd_text):
        if not self.is_connected or not self.ser or not self.ser.is_open:
            self._log_terminal(f"ERR: Cannot send '{cmd_text}' - Not connected!", "err")
            return

        # Ending formatting
        ending_type = self.append_newline.get()
        if ending_type == "\\n":
            payload = cmd_text.rstrip("\r\n") + "\n"
        elif ending_type == "\\r\\n":
            payload = cmd_text.rstrip("\r\n") + "\r\n"
        else:
            payload = cmd_text

        try:
            b = payload.encode("utf-8")
            self.ser.write(b)
            self.bytes_tx += len(b)
            self.status_counters_lbl.config(text=f"TX: {self.bytes_tx} B | RX: {self.bytes_rx} B")
            self._log_terminal(f"TX >> {cmd_text}", "tx")
        except Exception as e:
            self._log_terminal(f"ERR: Write failed: {e}", "err")

    # --------------------------------------------------------------------------
    # Terminal Logging & Display Helpers
    # --------------------------------------------------------------------------
    def _log_terminal(self, msg, tag="sys"):
        now_str = ""
        if self.show_timestamps.get():
            now_str = datetime.now().strftime("[%H:%M:%S.%f")[:-3] + "] "

        self.terminal.insert(tk.END, now_str, "dim")
        self.terminal.insert(tk.END, msg + "\n", tag)

        if self.autoscroll.get():
            self.terminal.see(tk.END)

    def _clear_console(self):
        self.terminal.delete("1.0", tk.END)

    def _save_log_dialog(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("JSON Lines", "*.jsonl"), ("All files", "*.*")],
            title="Save Terminal Log"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.terminal.get("1.0", tk.END))
                messagebox.showinfo("Log Saved", f"Successfully saved log to:\n{path}")
            except Exception as e:
                messagebox.showerror("Save Failed", f"Could not save file:\n{e}")

    # --------------------------------------------------------------------------
    # Command History Navigation (Up/Down)
    # --------------------------------------------------------------------------
    def _history_up(self, event=None):
        if not self.cmd_history:
            return "break"
        if self.history_index > 0:
            self.history_index -= 1
            self.cmd_input.delete(0, tk.END)
            self.cmd_input.insert(0, self.cmd_history[self.history_index])
        return "break"

    def _history_down(self, event=None):
        if not self.cmd_history:
            return "break"
        if self.history_index < len(self.cmd_history) - 1:
            self.history_index += 1
            self.cmd_input.delete(0, tk.END)
            self.cmd_input.insert(0, self.cmd_history[self.history_index])
        else:
            self.history_index = len(self.cmd_history)
            self.cmd_input.delete(0, tk.END)
        return "break"

    # --------------------------------------------------------------------------
    # Telemetry Polling
    # --------------------------------------------------------------------------
    def _toggle_polling(self):
        if self.poll_var.get():
            self._start_polling()
        else:
            self._stop_polling()

    def _start_polling(self):
        if self.polling_active:
            return
        self.polling_active = True
        self.stop_polling_event.clear()
        self.polling_thread = threading.Thread(target=self._polling_loop, daemon=True)
        self.polling_thread.start()
        self._log_terminal("SYS: Automatic telemetry polling started (every 600ms).", "sys")

    def _stop_polling(self):
        self.polling_active = False
        self.stop_polling_event.set()
        self.poll_var.set(False)

    def _polling_loop(self):
        while not self.stop_polling_event.is_set():
            if self.is_connected and self.ser and self.ser.is_open:
                try:
                    self.ser.write(b'{"T": 5}\n')
                    self.bytes_tx += 9
                except Exception:
                    pass
            time.sleep(0.6)

    # --------------------------------------------------------------------------
    # Macro / Batch Script Runner
    # --------------------------------------------------------------------------
    def _start_macro(self):
        if self.macro_running:
            return
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to serial port before running macro.")
            return

        lines = self.macro_text.get("1.0", tk.END).splitlines()
        self.macro_running = True
        self.stop_macro_event.clear()
        self.btn_run_macro.config(state=tk.DISABLED)
        self.btn_stop_macro.config(state=tk.NORMAL)

        threading.Thread(target=self._macro_execution_loop, args=(lines,), daemon=True).start()

    def _stop_macro(self):
        self.macro_running = False
        self.stop_macro_event.set()
        self.btn_run_macro.config(state=tk.NORMAL)
        self.btn_stop_macro.config(state=tk.DISABLED)

    def _macro_execution_loop(self, lines):
        self._log_terminal("SYS: Starting macro execution...", "sys")
        for line_raw in lines:
            if self.stop_macro_event.is_set():
                break

            line = line_raw.strip()
            if not line or line.startswith("//"):
                continue

            if line.startswith("#"):
                # Check for delay
                parts = line.split()
                if len(parts) >= 2 and parts[1].lower() == "delay":
                    try:
                        sec = float(parts[2])
                        self._log_terminal(f"SYS: Macro delay {sec}s...", "dim")
                        time.sleep(sec)
                    except Exception:
                        pass
                continue

            # Command line
            self.root.after(0, self.send_command_raw, line)
            time.sleep(0.2)

        self.root.after(0, self._stop_macro)
        self.root.after(0, self._log_terminal, "SYS: Macro execution finished.", "sys")

    # --------------------------------------------------------------------------
    # Clean Shutdown
    # --------------------------------------------------------------------------
    def _on_close(self):
        self._disconnect_port()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = RoArmSerialConsole(root)
    root.mainloop()


if __name__ == "__main__":
    main()
