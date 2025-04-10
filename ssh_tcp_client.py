# TCP Client (ssh_tcp_client.py)
import paramiko
import socket
import time
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SSHClientTCP:
    def __init__(self, host, port, username, password):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.channel = None
        self.connected = False
        self.connection_time = 0
        self.data_sent = 0
        self.data_received = 0
        
    def connect(self):
        """Connect to SSH server over TCP"""
        start_time = time.time()
        sock = None
        
        try:
            # Create client
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            logger.info(f"Connecting to {self.host}:{self.port} via TCP...")
            
            # Create socket first for better banner handling
            sock = socket.create_connection((self.host, self.port), timeout=20)
            logger.info("TCP socket connected, waiting for SSH banner")
            
            # Use much longer banner timeout and explicit connection parameters
            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=30,
                banner_timeout=60,  # Much longer banner timeout (1 minute)
                look_for_keys=False,  # Don't try to use SSH keys
                allow_agent=False,   # Don't use SSH agent
                sock=sock            # Use our pre-connected socket
            )
            
            logger.info("SSH connection established")
            
            # Get transport and open channel
            transport = self.client.get_transport()
            if not transport:
                raise Exception("No transport available after connect")
                
            self.channel = transport.open_session()
            if not self.channel:
                raise Exception("Failed to open session channel")
                
            self.channel.get_pty()
            self.channel.invoke_shell()
            
            # Wait for welcome message with a longer timeout
            time.sleep(2)  # Give server time to send welcome message
            output = b""
            if self.channel.recv_ready():
                output = self.channel.recv(1024)
            
            if output:
                logger.info(f"Server response: {output.decode('utf-8', errors='replace').strip()}")
            else:
                logger.warning("No initial server response received")
            
            self.connected = True
            self.connection_time = time.time() - start_time
            logger.info(f"Connected successfully in {self.connection_time:.2f} seconds")
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            # If we get a specific banner error, provide more details
            if "Error reading SSH protocol banner" in str(e):
                logger.error("SSH banner exchange failed. This likely means the server is not sending a proper SSH banner.")
                logger.error("Check that the server is correctly implementing the SSH protocol.")
            
            if sock:
                sock.close()
                
            self.connected = False
            return False
    
    def send_command(self, command):
        """Send command over SSH"""
        if not self.connected or not self.channel:
            logger.error("Not connected")
            return None
            
        try:
            start_time = time.time()
            
            # Send command
            command_bytes = (command + "\n").encode('utf-8')
            self.channel.send(command_bytes)
            self.data_sent += len(command_bytes)
            
            # Wait for response with improved handling
            time.sleep(1)  # Give server more time to respond
            output = b""
            wait_count = 0
            
            while wait_count < 20:  # Double the maximum wait time
                if self.channel.recv_ready():
                    chunk = self.channel.recv(1024)
                    output += chunk
                    self.data_received += len(chunk)
                    # If no more data and we have something, break
                    if not self.channel.recv_ready() and output:
                        break
                else:
                    wait_count += 1
                    time.sleep(0.1)
            
            execution_time = time.time() - start_time
            
            result = {
                'output': output.decode('utf-8', errors='replace'),
                'execution_time': execution_time
            }
            
            logger.info(f"Command executed in {execution_time:.2f} seconds")
            logger.info(f"Data sent: {len(command_bytes)} bytes, received: {len(output)} bytes")
            return result
            
        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}")
            return None
    
    def send_file(self, content, filename):
        """Simulate file transfer by sending content as a command"""
        if not self.connected:
            logger.error("Not connected")
            return None
            
        try:
            start_time = time.time()
            
            # Create a command that would store the content in a file
            cmd = f"Simulating file transfer: {filename} with {len(content)} bytes"
            result = self.send_command(cmd)
            
            transfer_time = time.time() - start_time
            
            file_stats = {
                'file_size': len(content),
                'transfer_time': transfer_time,
                'speed': len(content) / transfer_time if transfer_time > 0 else 0
            }
            
            logger.info(f"File transfer simulated in {transfer_time:.2f} seconds ({file_stats['speed']:.2f} bytes/sec)")
            return file_stats
            
        except Exception as e:
            logger.error(f"File transfer failed: {str(e)}")
            return None
    
    def run_benchmark(self, num_commands=10, file_size=1024*1024):
        """Run benchmark tests"""
        if not self.connected:
            logger.error("Not connected. Call connect() first.")
            return None
            
        results = {
            'connection_time': self.connection_time,
            'commands': [],
            'file_transfer': None
        }
        
        # Command benchmark
        logger.info(f"Running command benchmark ({num_commands} commands)...")
        for i in range(num_commands):
            command = f"echo This is test command {i}"
            result = self.send_command(command)
            if result:
                results['commands'].append(result['execution_time'])
        
        # File transfer benchmark
        logger.info(f"Running file transfer benchmark ({file_size} bytes)...")
        content = "X" * file_size
        transfer_result = self.send_file(content, "test_file.txt")
        if transfer_result:
            results['file_transfer'] = transfer_result
        
        return results
    
    def disconnect(self):
        """Close SSH connection"""
        if self.channel:
            self.channel.close()
        if self.client:
            self.client.close()
        self.connected = False
        logger.info("Connection closed")

def main():
    # Parse command line arguments
    host = '127.0.0.1'
    port = 2222
    username = 'test'
    password = 'test'
    
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    if len(sys.argv) > 3:
        username = sys.argv[3]
    if len(sys.argv) > 4:
        password = sys.argv[4]
    
    # Create SSH client and connect
    client = SSHClientTCP(host, port, username, password)
    
    # Try TCP connection
    if client.connect():
        # Run interactive session
        try:
            # Run benchmark
            results = client.run_benchmark(num_commands=5, file_size=1024*100)
            
            # Print results
            print("\nBenchmark Results:")
            print(f"Connection time: {results['connection_time']:.4f} seconds")
            
            if results['commands']:
                avg_cmd_time = sum(results['commands']) / len(results['commands'])
                print(f"Average command time: {avg_cmd_time:.4f} seconds")
            
            if results['file_transfer']:
                ft = results['file_transfer']
                print(f"File transfer: {ft['file_size']} bytes in {ft['transfer_time']:.4f} seconds")
                print(f"Transfer speed: {ft['speed']:.2f} bytes/second")
            
            # Send a few interactive commands
            client.send_command("ls -la")
            client.send_command("pwd")
            client.send_command("exit")
            
        finally:
            client.disconnect()
    else:
        logger.error("Failed to connect via TCP. Exiting.")

if __name__ == "__main__":
    main()