import serial
import serial.tools.list_ports
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

class SerialGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Serial Command Sender")
        self.root.geometry("620x500")

        self.ser = None
        self.running = False

        # --- Top Connection Bar ---
        conn_frame = ttk.LabelFrame(root, text="Connection", padding=10)
        conn_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(conn_frame, text="Port:").grid(row=0, column=0, padx=5, pady=2)
        self.port_combo = ttk.Combobox(conn_frame, width=15)
        self.port_combo.grid(row=0, column=1, padx=5, pady=2)

        ttk.Button(conn_frame, text="⟳", width=3, command=self.refresh_ports).grid(row=0, column=2, padx=2)

        ttk.Label(conn_frame, text="Baud:").grid(row=0, column=3, padx=5, pady=2)
        self.baud_combo = ttk.Combobox(conn_frame, width=10, values=[
            "9600", "19200", "38400", "57600", "115200", "230400", "921600"
        ])
        self.baud_combo.set("115200")
        self.baud_combo.grid(row=0, column=4, padx=5, pady=2)

        self.btn_connect = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.btn_connect.grid(row=0, column=5, padx=10, pady=2)

        # --- Output / Log Area ---
        log_frame = ttk.LabelFrame(root, text="Terminal Output", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.CHAR, bg="#1e1e1e", fg="#d4d4d4", font=("Courier", 10))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_config("tx", foreground="#4ec9b0")
        self.log_text.tag_config("rx", foreground="#ce9178")
        self.log_text.tag_config("sys", foreground="#569cd6")

        # --- Bottom Command Entry Bar ---
        send_frame = ttk.Frame(root, padding=10)
        send_frame.pack(fill="x", padx=10, pady=5)

        self.cmd_entry = ttk.Entry(send_frame)
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.cmd_entry.bind("<Return>", lambda event: self.send_command())

        # Line ending selection
        self.line_ending_var = tk.StringVar(value=r"\r\n")
        self.line_endings = ttk.Combobox(send_frame, width=6, textvariable=self.line_ending_var, state="readonly", values=[r"\r\n", r"\n", r"\r", "None"])
        self.line_endings.pack(side="left", padx=5)

        self.btn_send = ttk.Button(send_frame, text="Send", command=self.send_command, state="disabled")
        self.btn_send.pack(side="right")

        self.refresh_ports()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.current(0)

    def toggle_connection(self):
        if self.ser and self.ser.is_open:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        port = self.port_combo.get()
        baud = self.baud_combo.get()
        if not port:
            messagebox.showerror("Error", "No serial port selected.")
            return

        try:
            self.ser = serial.Serial(port, int(baud), timeout=0.1)
            self.running = True
            self.btn_connect.config(text="Disconnect")
            self.btn_send.config(state="normal")
            self.log(f"Connected to {port} @ {baud} bps\n", "sys")

            # Start reading daemon thread
            self.rx_thread = threading.Thread(target=self.read_serial, daemon=True)
            self.rx_thread.start()
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    def disconnect(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.btn_connect.config(text="Connect")
        self.btn_send.config(state="disabled")
        self.log("Disconnected\n", "sys")

    def send_command(self):
        if not self.ser or not self.ser.is_open:
            return
        cmd = self.cmd_entry.get()
        suffix = {"\\r\\n": "\r\n", "\\n": "\n", "\\r": "\r", "None": ""}.get(self.line_ending_var.get(), "")
        payload = (cmd + suffix).encode('utf-8')
        try:
            self.ser.write(payload)
            self.log(f"> {cmd}\n", "tx")
            self.cmd_entry.delete(0, tk.END)
        except Exception as e:
            self.log(f"Send failed: {e}\n", "sys")

    def read_serial(self):
        while self.running:
            if self.ser and self.ser.is_open:
                try:
                    data = self.ser.read(self.ser.in_waiting or 1)
                    if data:
                        text = data.decode('utf-8', errors='replace')
                        self.log(text, "rx")
                except Exception:
                    break

    def log(self, text, tag="rx"):
        self.log_text.insert(tk.END, text, tag)
        self.log_text.see(tk.END)

    def on_close(self):
        self.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = SerialGUI(root)
    root.mainloop()
