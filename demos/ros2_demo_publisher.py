#!/usr/bin/env python3
"""
Waveshare RoArm-M1 ROS 2 Automated Joint Trajectory Publisher Demo
===================================================================
Publishes dynamic joint trajectories to the `/joint_states` topic.
Visualizes in RViz2 (`ros2 launch roarm roarm.launch.py gui:=False`)
and drives physical arm when running `ros2 run serial_ctrl serial_ctrl`.

Joint Names:
    - base_to_L1        (Joint 1, base pan: -3.14 to 3.14 rad)
    - L1_to_L2          (Joint 2, shoulder: -1.05 to 1.05 rad)
    - L2_to_L3          (Joint 3, elbow: -2.7 to 2.7 rad)
    - L3_to_L4          (Joint 4, wrist: -2.1 to 2.1 rad)
    - L4_to_L5_1_A      (Joint 5, gripper clamp: -1.57 to 0 rad)

Usage:
    python3 ros2_demo_publisher.py
"""

import sys
import time
import math

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import JointState
    HAS_ROS2 = True
except ImportError:
    HAS_ROS2 = False


if not HAS_ROS2:
    print("\n[WARNING] ROS 2 (rclpy) is not sourced in the current Python environment.")
    print("To run this ROS 2 demo, first source your ROS 2 environment, e.g.:")
    print("    source /opt/ros/<distro>/setup.bash")
    print("    python3 ros2_demo_publisher.py\n")


class RoArmTrajectoryPublisher(Node if HAS_ROS2 else object):
    def __init__(self):
        if not HAS_ROS2:
            return
        super().__init__('roarm_demo_trajectory_publisher')
        self.publisher_ = self.create_publisher(JointState, 'joint_states', 10)
        self.timer_period = 0.05  # 20 Hz
        self.timer = self.create_timer(self.timer_period, self.timer_callback)
        self.start_time = time.time()
        self.get_logger().info("RoArm-M1 Demo Trajectory Publisher started. Publishing to /joint_states at 20Hz.")

    def timer_callback(self):
        elapsed = time.time() - self.start_time
        
        # Smooth sinusoidal waving and dancing trajectory
        q1 = 0.6 * math.sin(0.8 * elapsed)           # Base pan
        q2 = 0.35 * math.sin(0.6 * elapsed)          # Shoulder
        q3 = 0.5 * math.cos(0.7 * elapsed)           # Elbow
        q4 = 0.4 * math.sin(1.2 * elapsed)           # Wrist
        q5 = -0.7 + 0.7 * math.sin(1.5 * elapsed)    # Gripper (-1.4 to 0 rad)

        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = [
            'base_to_L1',
            'L1_to_L2',
            'L2_to_L3',
            'L3_to_L4',
            'L4_to_L5_1_A'
        ]
        msg.position = [q1, q2, q3, q4, q5]
        msg.velocity = []
        msg.effort = []

        self.publisher_.publish(msg)


def main(args=None):
    if not HAS_ROS2:
        sys.exit(1)
    rclpy.init(args=args)
    node = RoArmTrajectoryPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Stopping ROS 2 demo trajectory publisher...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
