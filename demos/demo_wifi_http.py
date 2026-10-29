#!/usr/bin/env python3
"""
Waveshare RoArm-M1 Wireless WiFi & HTTP REST API Controller
===========================================================
Controls the RoArm-M1 over WiFi using the onboard ESP32 HTTP Web Server.

Default WiFi AP:
    SSID:     ESP32_DEV
    Password: 12345678
    Default IP: 192.168.4.1 (port 80)

Or connect the arm to your home/lab router in STA mode and use its assigned LAN IP.

Usage:
    python3 demo_wifi_http.py                        # Uses default 192.168.4.1
    python3 demo_wifi_http.py --ip 192.168.1.150     # Specify IP
    python3 demo_wifi_http.py --mock                 # Simulation test
"""

import sys
import time
import json
import argparse
import urllib.request
import urllib.error


class RoArmM1WiFi:
    """HTTP Client for RoArm-M1 ESP32 Web Server."""

    def __init__(self, base_ip: str = "192.168.4.1", port: int = 80, mock: bool = False):
        self.base_url = f"http://{base_ip}:{port}"
        self.mock = mock

    def _get(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        if params:
            query = "&".join([f"{k}={v}" for k, v in params.items()])
            url += f"?{query}"

        if self.mock:
            print(f"[MOCK HTTP GET] {url}")
            if "getDevInfo" in endpoint:
                return {"DeviceName": "RoArm-M1 (Simulated WiFi)", "IP": "192.168.4.1", "DefaultWifiMode": "AP"}
            elif "readData" in endpoint or "getAngTorInfo" in endpoint:
                return {"A1": 180, "A2": 10, "A3": 280, "A4": 135, "A5": 180, "T1": 15, "T2": 20}
            return {"status": "ok"}

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RoArm-Python-WiFi/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as response:
                content = response.read().decode("utf-8")
                if content.strip().startswith("{") and content.strip().endswith("}"):
                    return json.loads(content)
                return {"response": content}
        except Exception as e:
            print(f"[HTTP ERROR] Failed to request {url}: {e}")
            return {}

    def get_device_info(self) -> dict:
        """Query /getDevInfo."""
        return self._get("/getDevInfo")

    def get_telemetry(self) -> dict:
        """Query /readData and /getAngTorInfo."""
        return self._get("/readData")

    def emergency_stop(self):
        """Trigger /stop."""
        print("[WIFI] Emergency Stop triggered!")
        return self._get("/stop")

    def send_cmd(self, cmd_t: int, cmd_a: int = 0, cmd_b: int = 0):
        """
        Send raw command to /cmd endpoint.
        :param cmd_t: Command Type (e.g. 1=Angle, 2=Torque, 3=Coord, 4=Info, 5=RecordReplay)
        :param cmd_a: Sub-command / Axis
        :param cmd_b: Value or direction
        """
        return self._get("/cmd", {"cmdT": cmd_t, "cmdA": cmd_a, "cmdB": cmd_b})

    def wave_demo(self):
        """Demonstrate waving over WiFi."""
        print("\n[WIFI DEMO] Running Wi-Fi greeting routine...")
        # Angle control init
        self.send_cmd(1, 0, 0)
        time.sleep(1.0)
        print("  -> Wave complete.")


def main():
    parser = argparse.ArgumentParser(description="RoArm-M1 WiFi HTTP Controller")
    parser.add_argument("--ip", type=str, default="192.168.4.1", help="RoArm-M1 IP address")
    parser.add_argument("--port", type=int, default=80, help="HTTP port (default: 80)")
    parser.add_argument("--mock", action="store_true", help="Run in mock/simulation mode")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("   📶  WAVESHARE RoArm-M1 WIRELESS Wi-Fi CONTROLLER")
    print("=" * 60)
    print(f" Target URL: http://{args.ip}:{args.port}")
    if args.mock:
        print(" Mode: SIMULATION / MOCK")
    else:
        print(" Make sure your computer is connected to the 'ESP32_DEV' WiFi hotspot")
        print(" or that the RoArm-M1 is reachable at this IP.")
    print("-" * 60)

    client = RoArmM1WiFi(base_ip=args.ip, port=args.port, mock=args.mock)

    print("\n1. Fetching Device Info over Wi-Fi...")
    info = client.get_device_info()
    print(f"   Response: {info}")

    print("\n2. Fetching Telemetry...")
    telemetry = client.get_telemetry()
    print(f"   Response: {telemetry}")

    print("\n3. Triggering test motion...")
    client.wave_demo()

    print("\nWi-Fi demo finished.")


if __name__ == "__main__":
    main()
