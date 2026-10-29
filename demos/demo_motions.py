#!/usr/bin/env python3
"""
Waveshare RoArm-M1 Physical Motor Motion Demonstration
======================================================
Strictly controls the PHYSICAL robot arm motors via serial UART (/dev/ttyUSB0).
No simulation or mock mode.

Demonstration Sequence:
1. Real-time Telemetry & Servo Health Check (T: 4 & T: 5)
2. Home Neutral Pose Alignment (T: 11)
3. Physical Gripper Clamp & Release Cycle
4. Physical Base Pan Rotation Sweep (Joint 1)
5. Physical Forearm Elevation & Waving Salute (Joints 2, 3, 4)
6. 3D Cartesian Pick-and-Place Routine (Inverse Kinematics T: 2)
7. Safe Parking Neutral Stance

Usage:
    python3 demo_motions.py
    python3 demo_motions.py --port /dev/ttyUSB0
    python3 demo_motions.py --loop
"""

import sys
import time
import argparse
from roarm_driver import RoArmM1, logger


def print_banner(title: str):
    print("\n" + "=" * 65)
    print(f"  🦾  {title}")
    print("=" * 65)


def run_diagnostics(arm: RoArmM1):
    print_banner("STEP 1: Physical Servo Telemetry & Health")
    info = arm.get_device_info()
    if info:
        print(f"  • Device Name:     {info.get('DevName', 'RoArm-M1')}")
        print(f"  • MAC Address:     {info.get('MAC', 'N/A')}")
        print(f"  • AP Network:      {info.get('AP_SSID', 'N/A')}")
    else:
        print("  • Device info query timed out.")

    angles_torques = arm.get_angles_and_torque()
    if angles_torques:
        print("  • Physical Servo Feedback (Positions & Motor Loads):")
        for i in range(1, 6):
            ang = angles_torques.get(f"A{i}", "N/A")
            tor = angles_torques.get(f"T{i}", "N/A")
            print(f"     - Joint {i}: Angle = {ang}°, Load = {tor}")
    time.sleep(1.0)


def run_homing(arm: RoArmM1):
    print_banner("STEP 2: Moving Motors to Calibrated Neutral Pose")
    print("  -> Sending Home command (T: 11)...")
    arm.reset_joint_angles(wait=1.8)
    print("  -> Physical motors aligned in neutral home position.")


def run_gripper_test(arm: RoArmM1):
    print_banner("STEP 3: Physical Gripper Action")
    print("  -> Opening gripper clamp (180°)...")
    arm.open_gripper(speed=300, wait=1.0)

    print("  -> Closing gripper clamp (360°)...")
    arm.close_gripper(speed=300, wait=1.0)

    print("  -> Opening gripper clamp (180°)...")
    arm.open_gripper(speed=300, wait=1.0)


def run_base_pan_sweep(arm: RoArmM1):
    print_banner("STEP 4: Base Rotation Sweep (Joint 1 Motor)")
    print("  -> Rotating Base to Left (+30°)...")
    arm.set_joint_angles(210, 0, 90, 90, 180, speed=200, wait=1.2)

    print("  -> Rotating Base to Right (-30°)...")
    arm.set_joint_angles(150, 0, 90, 90, 180, speed=200, wait=1.5)

    print("  -> Returning Base to Center (180°)...")
    arm.set_joint_angles(180, 0, 90, 90, 180, speed=200, wait=1.2)


def run_wave_gesture(arm: RoArmM1):
    print_banner("STEP 5: Physical Wave & Salute Gesture")
    print("  -> Raising shoulder and forearm to salute posture...")
    # Base: 180, Shoulder: 45, Elbow: 60, Wrist: 100, Gripper: 180
    arm.set_joint_angles(180, 45, 60, 100, 180, speed=250, wait=1.2)

    print("  -> Waving forearm left and right 3 times...")
    for i in range(3):
        print(f"     Wave {i+1}/3...")
        arm.set_joint_angles(205, 45, 60, 120, 180, speed=350, wait=0.6)
        arm.set_joint_angles(155, 45, 60, 80, 180, speed=350, wait=0.6)

    # Return to upright greeting center
    arm.set_joint_angles(180, 45, 60, 100, 180, speed=250, wait=0.8)


def run_cartesian_pick_and_place(arm: RoArmM1):
    print_banner("STEP 6: Physical 3D Cartesian Pick-and-Place")
    print("  (Inverse Kinematics T:2 calculated onboard ESP32)")
    
    # 3D Coordinates (in mm)
    PICK_X, PICK_Y = 240.0, -90.0
    PLACE_X, PLACE_Y = 240.0, 90.0
    HOVER_Z = 220.0
    PICK_Z = 120.0
    PITCH_THETA = 90.0

    print("  -> 1. Initializing Cartesian mode (T: 12)...")
    arm.reset_cartesian_coords(wait=1.2)

    print(f"  -> 2. Moving arm to hover above Pickup point ({PICK_X}, {PICK_Y}, {HOVER_Z})...")
    arm.set_cartesian_coords(PICK_X, PICK_Y, HOVER_Z, theta=PITCH_THETA, gripper=180.0, step_delay=10, wait=1.2)

    print(f"  -> 3. Lowering gripper to pick height (Z={PICK_Z} mm)...")
    arm.set_cartesian_coords(PICK_X, PICK_Y, PICK_Z, theta=PITCH_THETA, gripper=180.0, step_delay=10, wait=1.0)

    print("  -> 4. Closing gripper clamp to grasp object...")
    arm.set_cartesian_coords(PICK_X, PICK_Y, PICK_Z, theta=PITCH_THETA, gripper=360.0, step_delay=10, wait=0.8)

    print(f"  -> 5. Lifting object to clearance height (Z={HOVER_Z} mm)...")
    arm.set_cartesian_coords(PICK_X, PICK_Y, HOVER_Z, theta=PITCH_THETA, gripper=360.0, step_delay=10, wait=1.0)

    print(f"  -> 6. Swinging across to Place point ({PLACE_X}, {PLACE_Y}, {HOVER_Z})...")
    arm.set_cartesian_coords(PLACE_X, PLACE_Y, HOVER_Z, theta=PITCH_THETA, gripper=360.0, step_delay=10, wait=1.5)

    print(f"  -> 7. Lowering object to release height (Z={PICK_Z} mm)...")
    arm.set_cartesian_coords(PLACE_X, PLACE_Y, PICK_Z, theta=PITCH_THETA, gripper=360.0, step_delay=10, wait=1.0)

    print("  -> 8. Opening gripper to release object...")
    arm.set_cartesian_coords(PLACE_X, PLACE_Y, PICK_Z, theta=PITCH_THETA, gripper=180.0, step_delay=10, wait=0.8)

    print("  -> 9. Retracting up to safe clearance height...")
    arm.set_cartesian_coords(PLACE_X, PLACE_Y, HOVER_Z, theta=PITCH_THETA, gripper=180.0, step_delay=10, wait=1.0)


def run_park_and_standby(arm: RoArmM1):
    print_banner("STEP 7: Safe Home Parking & Standby")
    print("  -> Returning arm to calibrated neutral stance (T: 11)...")
    arm.reset_joint_angles(wait=1.5)
    print("  -> All physical motors secured in parked standby position.")


def main():
    parser = argparse.ArgumentParser(description="Waveshare RoArm-M1 Physical Motion Demo")
    parser.add_argument("--port", type=str, default="/dev/ttyUSB0", help="Serial port (default: /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--loop", action="store_true", help="Run demo continuously in a loop")
    args = parser.parse_args()

    print("\n" + "#" * 65)
    print("   🦾 WAVESHARE RoArm-M1 - PHYSICAL MOTOR MOTION DEMO")
    print("   [MODE: STRICTLY PHYSICAL HARDWARE - NO SIMULATION]")
    print("#" * 65)

    # Connect strictly to physical hardware - will raise error if not available
    arm = RoArmM1(port=args.port, baudrate=args.baud, mock=False)

    iteration = 1
    try:
        while True:
            if args.loop:
                print(f"\n--- Starting Physical Demo Cycle #{iteration} ---")

            run_diagnostics(arm)
            run_homing(arm)
            run_gripper_test(arm)
            run_base_pan_sweep(arm)
            run_wave_gesture(arm)
            run_cartesian_pick_and_place(arm)
            run_park_and_standby(arm)

            if not args.loop:
                break
            iteration += 1
            print("\nPausing 3 seconds before next cycle (Press Ctrl+C to stop)...")
            time.sleep(3.0)

        print("\n" + "=" * 65)
        print("  🎉 Physical Motor Demo Completed Successfully!")
        print("=" * 65 + "\n")

    except KeyboardInterrupt:
        print("\n\n[USER STOP] Halting physical motors safely...")
        arm.emergency_stop()
    finally:
        arm.close()


if __name__ == "__main__":
    main()
