#!/usr/bin/env python3
"""
Waveshare RoArm-M1 Interactive Control Console
==============================================
Provides a hands-on terminal menu to jog joints, control Cartesian coordinates,
record and replay taught positions, toggle torques, and trigger action presets.

Usage:
    python3 demo_interactive.py
    python3 demo_interactive.py --port /dev/ttyUSB0
    python3 demo_interactive.py --mock
"""

import sys
import time
import argparse
from roarm_driver import RoArmM1


def clear_line():
    sys.stdout.write("\033[K")


def prompt_float(prompt_text: str, default_val: float) -> float:
    try:
        val = input(f"{prompt_text} [{default_val}]: ").strip()
        return float(val) if val else default_val
    except ValueError:
        print("Invalid number. Using default.")
        return default_val


def prompt_int(prompt_text: str, default_val: int) -> int:
    try:
        val = input(f"{prompt_text} [{default_val}]: ").strip()
        return int(val) if val else default_val
    except ValueError:
        print("Invalid integer. Using default.")
        return default_val


def menu_jog_joints(arm: RoArmM1):
    print("\n--- Joint Angle Jogger (Degrees) ---")
    print(f"Current Angles: J1={arm.current_angles[0]}°, J2={arm.current_angles[1]}°, "
          f"J3={arm.current_angles[2]}°, J4={arm.current_angles[3]}°, Gripper={arm.current_angles[4]}°")
    p1 = prompt_float("Enter Joint 1 (Base Pan 0-360°)", arm.current_angles[0])
    p2 = prompt_float("Enter Joint 2 (Shoulder)", arm.current_angles[1])
    p3 = prompt_float("Enter Joint 3 (Elbow)", arm.current_angles[2])
    p4 = prompt_float("Enter Joint 4 (Wrist Pitch)", arm.current_angles[3])
    p5 = prompt_float("Enter Joint 5 (Gripper 90=close, 180=open)", arm.current_angles[4])
    speed = prompt_int("Enter speed (50-500)", 200)

    print(f"Sending Joint Angles -> ({p1}, {p2}, {p3}, {p4}, {p5})...")
    arm.set_joint_angles(p1, p2, p3, p4, p5, speed=speed, wait=0.5)
    print("Motion finished.")


def menu_jog_cartesian(arm: RoArmM1):
    print("\n--- Cartesian Coordinate Jogger (mm) ---")
    print(f"Current Coords: X={arm.current_coords[0]:.1f}, Y={arm.current_coords[1]:.1f}, "
          f"Z={arm.current_coords[2]:.1f}, Pitch={arm.current_coords[3]:.1f}°, Gripper={arm.current_coords[4]:.1f}°")
    x = prompt_float("Enter X (mm, reach forward)", arm.current_coords[0])
    y = prompt_float("Enter Y (mm, left/right)", arm.current_coords[1])
    z = prompt_float("Enter Z (mm, height)", arm.current_coords[2])
    theta = prompt_float("Enter Pitch Theta (deg)", arm.current_coords[3])
    gripper = prompt_float("Enter Gripper (90=close, 180=open)", arm.current_coords[4])
    step_delay = prompt_int("Enter interpolation step delay (ms, default 10)", 10)

    print(f"Sending Cartesian Target -> X={x}, Y={y}, Z={z}, Theta={theta}°...")
    arm.set_cartesian_coords(x, y, z, theta=theta, gripper=gripper, step_delay=step_delay, wait=0.8)
    print("Target reached.")


def menu_gripper(arm: RoArmM1):
    print("\n--- Gripper Controls ---")
    print("  [1] Open Gripper Fully (180°)")
    print("  [2] Close Gripper Clamp (90°)")
    print("  [3] Custom Gripper Angle")
    choice = input("Select: ").strip()
    if choice == "1":
        arm.open_gripper(wait=0.4)
        print("Gripper opened.")
    elif choice == "2":
        arm.close_gripper(wait=0.4)
        print("Gripper closed.")
    elif choice == "3":
        ang = prompt_float("Enter angle (90=close, 180=open)", 135.0)
        arm.set_gripper(ang, wait=0.4)
        print(f"Gripper set to {ang}°.")


def menu_teach_replay(arm: RoArmM1):
    print("\n=== Teach & Replay Mode (Direct Hardware Teaching) ===")
    print("This mode unlocks the servo torque so you can hand-position the arm,")
    print("record waypoints into the ESP32 Flash memory, and replay them automatically.")
    print("\nOptions:")
    print("  [1] Unlock torque (Torque OFF) - Move arm freely by hand")
    print("  [2] Lock torque (Torque ON)")
    print("  [3] Record current pose as step N")
    print("  [4] Move to step N")
    print("  [5] Replay recorded trajectory")
    choice = input("Select: ").strip()
    if choice == "1":
        arm.set_torque(False)
        print("Torque unlocked! You can now gently move the arm with your hands.")
    elif choice == "2":
        arm.set_torque(True)
        print("Torque locked!")
    elif choice == "3":
        step_num = prompt_int("Enter Step Number (1-20)", 1)
        arm.record_step(step_num)
        print(f"Recorded step {step_num} successfully.")
    elif choice == "4":
        step_num = prompt_int("Enter Step Number to move to", 1)
        arm.move_to_step(step_num)
        print(f"Moving to step {step_num}...")
    elif choice == "5":
        loops = prompt_int("Enter loop count (1 for once, -1 for continuous)", 1)
        delay = prompt_int("Delay between steps in ms", 500)
        arm.replay_recorded_steps(step_delay=delay, loop_count=loops)


def menu_telemetry(arm: RoArmM1):
    print("\n--- Telemetry & Diagnostics ---")
    info = arm.get_device_info()
    if info:
        print(f"  • Device Info:     {info}")
    fb = arm.get_angles_and_torque()
    if fb:
        print("  • Joint Feedback:")
        for i in range(1, 6):
            print(f"     - Joint {i}: Angle = {fb.get(f'A{i}', 'N/A')}°, Load = {fb.get(f'T{i}', 'N/A')}")
    else:
        print("  • No feedback received (query timed out).")


def print_main_menu(arm: RoArmM1):
    print("\n" + "=" * 55)
    print("      🦾  Waveshare RoArm-M1 Interactive Console")
    print("=" * 55)
    print(f"  Status: {'MOCK/SIMULATED' if arm.is_mock else f'CONNECTED ({arm.port})'}")
    print(f"  Torque: {'LOCKED (ON)' if arm.torque_enabled else 'UNLOCKED (OFF)'}")
    print("-" * 55)
    print("  [1] Jog Joint Angles (Degrees)")
    print("  [2] Jog Cartesian Coordinates (X, Y, Z mm)")
    print("  [3] Gripper (Open / Close / Angle)")
    print("  [4] Teach & Replay (Hand Positioning)")
    print("  [5] Presets: Home Pose (T:11)")
    print("  [6] Presets: Cartesian Neutral (T:12)")
    print("  [7] Presets: Wave Greeting Routine")
    print("  [8] Toggle Motor Torque Lock (ON / OFF)")
    print("  [9] Read Telemetry & Sensor Feedback")
    print("  [0] Emergency Stop (Torque OFF)")
    print("  [Q] Quit")
    print("=" * 55)


def main():
    parser = argparse.ArgumentParser(description="RoArm-M1 Physical Interactive Console")
    parser.add_argument("--port", type=str, default="/dev/ttyUSB0", help="Serial port path (default: /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    args = parser.parse_args()

    arm = RoArmM1(port=args.port, baudrate=args.baud, mock=False)

    try:
        while True:
            print_main_menu(arm)
            choice = input("Enter choice: ").strip().lower()

            if choice == "1":
                menu_jog_joints(arm)
            elif choice == "2":
                menu_jog_cartesian(arm)
            elif choice == "3":
                menu_gripper(arm)
            elif choice == "4":
                menu_teach_replay(arm)
            elif choice == "5":
                arm.reset_joint_angles()
                print("Reset to Home Joint Angles.")
            elif choice == "6":
                arm.reset_cartesian_coords()
                print("Reset to Cartesian Initial Coordinates.")
            elif choice == "7":
                print("Running Greeting Wave...")
                arm.set_joint_angles(180, 45, 60, 100, 180, speed=300, wait=0.8)
                arm.set_joint_angles(205, 45, 60, 120, 180, speed=350, wait=0.4)
                arm.set_joint_angles(155, 45, 60, 80, 180, speed=350, wait=0.4)
                arm.set_joint_angles(180, 45, 60, 100, 180, speed=300, wait=0.5)
                arm.reset_joint_angles()
                print("Greeting done.")
            elif choice == "8":
                arm.set_torque(not arm.torque_enabled)
            elif choice == "9":
                menu_telemetry(arm)
            elif choice == "0":
                arm.emergency_stop()
            elif choice in ["q", "quit", "exit"]:
                print("Exiting interactive console. Goodbye!")
                break
            else:
                print("Unknown command. Please select an option from the menu.")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        arm.emergency_stop()
    finally:
        arm.close()


if __name__ == "__main__":
    main()
