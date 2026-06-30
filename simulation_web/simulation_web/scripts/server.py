#!/usr/bin/env python3
"""ROS2 Web Simulation Server for NAVERA"""

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import String
import threading
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from ament_index_python.packages import get_package_share_directory

class SimulationWebNode(Node):
    def __init__(self):
        super().__init__('simulation_web_node')
        
        self.declare_parameter('web_port', 8080)
        self.declare_parameter('web_host', '0.0.0.0')
        
        self.web_port = self.get_parameter('web_port').value
        self.web_host = self.get_parameter('web_host').value
        
        try:
            self.pkg_dir = get_package_share_directory('simulation_web')
            self.resources_dir = os.path.join(self.pkg_dir, 'resources')
        except:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.resources_dir = os.path.join(script_dir, '..', 'resources')
        
        self.get_logger().info(f'🚀 Web Server on {self.web_host}:{self.web_port}')
        self.get_logger().info(f'   Serving from: {self.resources_dir}')
        
        self.status_pub = self.create_publisher(String, 'simulation_web/status', 10)
        self.create_timer(1.0, self.timer_callback)
        self.start_http_server()
    
    def timer_callback(self):
        msg = String()
        msg.data = f"running on port {self.web_port}"
        self.status_pub.publish(msg)
    
    def start_http_server(self):
        node_ref = self
        
        class NaverHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(node_ref.resources_dir), **kwargs)
            
            def do_GET(self):
                # Rediriger / vers navera.html
                if self.path == '/':
                    self.path = '/navera.html'
                return super().do_GET()
            
            def end_headers(self):
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                super().end_headers()
            
            def log_message(self, fmt, *args):
                # Ignorer les erreurs favicon
                if 'favicon' in str(args):
                    return
                node_ref.get_logger().info(fmt % args)
        
        try:
            self.server = HTTPServer((self.web_host, self.web_port), NaverHandler)
            self.server_thread = threading.Thread(
                target=self.server.serve_forever,
                daemon=True
            )
            self.server_thread.start()
            self.get_logger().info(f'✅ HTTP Server running on {self.web_host}:{self.web_port}')
            self.get_logger().info(f'   🌐 Open: http://localhost:{self.web_port}/navera.html')
        except Exception as e:
            self.get_logger().error(f'❌ Server error: {e}')

def main(args=None):
    rclpy.init(args=args)
    node = SimulationWebNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    
    try:
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info('Shutdown')
    finally:
        executor.shutdown()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
