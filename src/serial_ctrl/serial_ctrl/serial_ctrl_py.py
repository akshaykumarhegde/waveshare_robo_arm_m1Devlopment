import rclpy
from rclpy.node import Node
import json
import serial
import serial.tools.list_ports
from sensor_msgs.msg import JointState


class MinimalSubscriber(Node):

    def __init__(self):
        super().__init__('serial_ctrl')
        
        self.declare_parameter('serial_port', '/dev/ttyUSB0')
        self.declare_parameter('baudrate', 115200)

        port = self.get_parameter('serial_port').get_parameter_value().string_value
        baudrate = self.get_parameter('baudrate').get_parameter_value().integer_value

        self.ser = None
        try:
            self.ser = serial.Serial(port, baudrate, timeout=0.5)
            self.get_logger().info(f"Connected to RoArm-M1 on {port} at {baudrate} baud.")
        except Exception as e:
            self.get_logger().warn(
                f"Could not open serial port '{port}': {e}. "
                "Running in Mock / Simulation Mode. (Specify port with --ros-args -p serial_port:=/dev/ttyUSB0)"
            )
            
        self.subscription = self.create_subscription(
            JointState,
            'joint_states',
            self.listener_callback,
            10
        )
        self.subscription  # prevent unused variable warning
    
    def posGet(self, radInput, direcInput, multiInput):
        if radInput == 0:
            return 2047
        else:
            getPos = int(2047 + (direcInput * radInput / 3.1415926 * 2048 * multiInput) + 0.5)
            return max(0, min(4095, getPos))

    def listener_callback(self, msg):
        a = msg.position
        if len(a) < 5:
            return
        
        join1 = self.posGet(a[0], -1, 1)
        join2 = self.posGet(a[1], -1, 3)
        join3 = self.posGet(a[2], -1, 1)
        join4 = self.posGet(a[3],  1, 1)
        join5 = self.posGet(a[4], -1, 1)
        
        data = json.dumps({
            'T': 3,
            'P1': join1, 'P2': join2, 'P3': join3, 'P4': join4, 'P5': join5,
            'S1': 0, 'S2': 0, 'S3': 0, 'S4': 0, 'S5': 0,
            'A1': 60, 'A2': 60, 'A3': 60, 'A4': 60, 'A5': 60
        }) + "\n"
        
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(data.encode('utf-8'))
            except Exception as e:
                self.get_logger().error(f"Serial write error: {e}")
        else:
            self.get_logger().debug(f"[MOCK TX] {data.strip()}")


def main(args=None):
    rclpy.init(args=args)
    minimal_subscriber = MinimalSubscriber()
    try:
        rclpy.spin(minimal_subscriber)
    except KeyboardInterrupt:
        pass
    finally:
        if minimal_subscriber.ser and minimal_subscriber.ser.is_open:
            minimal_subscriber.ser.close()
        minimal_subscriber.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
