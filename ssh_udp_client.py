# UDP Client (ssh_udp_client.py)
import socket
import sys
import time
import logging
import json
import hashlib
import queue
import threading
import random

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SSHClientUDP:
    """SSH client implementation over UDP"""
    
    PACKET_SIZE = 1400
    HEADER_SIZE = 200
    DATA_SIZE = PACKET_SIZE - HEADER_SIZE
    TIMEOUT = 1.0
    MAX_RETRIES = 5
    
    def __init__(self, host, port, username, password):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.session_id = ""
        self.sequence_number = 0
        self.server_addr = (host, port)
        self.connected = False
        self.connection_time = 0
        self.ack_queue = queue.Queue()
        self.data_queue = queue.Queue()
        self.receiver_thread = None
        self.running = False
        self.data_sent = 0
        self.data_received = 0
        
    def _create_packet(self, data, seq_num, packet_type="DATA"):
        """Create a packet with header and data"""
        if isinstance(data, str):
            data = data.encode('utf-8')
            
        # Create a header with sequence number, checksum, and packet type
        checksum = hashlib.md5(data).hexdigest()
        header = json.dumps({
            'seq': seq_num,
            'checksum': checksum,
            'type': packet_type,
            'length': len(data),
            'session': self.session_id
        }).encode('utf-8')
        
        # Pad header to fixed size
        header = header.ljust(self.HEADER_SIZE, b' ')
        
        # Combine header and data
        packet = header + data
        self.data_sent += len(packet)
        return packet
    
    def _parse_packet(self, packet):
        """Parse received packet into header and data"""
        header = packet[:self.HEADER_SIZE].strip()
        data = packet[self.HEADER_SIZE:]
        
        try:
            header_info = json.loads(header.decode('utf-8'))
            
            # Verify checksum for data packets
            if header_info['type'] not in ["ACK", "CONNECT_ACK"]:
                calculated_checksum = hashlib.md5(data).hexdigest()
                if header_info['checksum'] != calculated_checksum:
                    logger.warning(f"Checksum mismatch for packet {header_info['seq']}")
                    return None
                    
            self.data_received += len(packet)
            return {
                'seq': header_info['seq'],
                'type': header_info['type'],
                'length': header_info['length'] if 'length' in header_info else 0,
                'session': header_info.get('session', ""),
                'data': data[:header_info['length']] if 'length' in header_info else data
            }
        except Exception as e:
            logger.error(f"Error parsing packet: {str(e)}")
            return None
    
    def receiver(self):
        """Thread to receive packets from server"""
        self.socket.settimeout(0.5)
        
        while self.running:
            try:
                data, addr = self.socket.recvfrom(self.PACKET_SIZE)
                packet = self._parse_packet(data)
                
                if not packet:
                    continue
                
                if packet['type'] == "ACK":
                    # Put ACK in queue for send_reliable to process
                    self.ack_queue.put(packet['seq'])
                    logger.debug(f"Received ACK for packet {packet['seq']}")
                
                elif packet['type'] == "CONNECT_ACK":
                    # Store session ID if not already set
                    if not self.session_id:
                        self.session_id = packet['session']
                    logger.info(f"Connection established with session ID: {self.session_id}")
                    
                elif packet['type'] in ["DATA", "LAST"]:
                    # Send acknowledgment
                    ack_packet = self._create_packet(b"ACK", packet['seq'], packet_type="ACK")
                    self.socket.sendto(ack_packet, self.server_addr)
                    
                    # Process data
                    self.data_queue.put(packet['data'])
                    logger.debug(f"Received data packet {packet['seq']}")
                    
            except socket.timeout:
                pass
            except Exception as e:
                logger.error(f"Error in receiver: {str(e)}")
    
    def connect(self):
        """Connect to SSH server over UDP"""
        start_time = time.time()
        
        try:
            # Start receiver thread
            self.running = True
            self.receiver_thread = threading.Thread(target=self.receiver)
            self.receiver_thread.daemon = True
            self.receiver_thread.start()
            
            # Send connection request
            connect_packet = self._create_packet(b"CONNECT", 0, packet_type="CONNECT")
            
            # Try multiple times
            for attempt in range(self.MAX_RETRIES):
                logger.info(f"Connecting to {self.host}:{self.port} via UDP (attempt {attempt+1})...")
                self.socket.sendto(connect_packet, self.server_addr)
                
                # Wait for connection acknowledgment
                timeout = time.time() + self.TIMEOUT
                while time.time() < timeout:
                    if self.session_id:
                        self.connected = True
                        self.connection_time = time.time() - start_time
                        logger.info(f"Connected successfully in {self.connection_time:.2f} seconds")
                        
                        # Wait for welcome message
                        welcome_timeout = time.time() + 2.0
                        while time.time() < welcome_timeout:
                            try:
                                if not self.data_queue.empty():
                                    welcome = self.data_queue.get(timeout=1.0)
                                    logger.info(f"Server welcome: {welcome.decode('utf-8').strip()}")
                                    break
                            except queue.Empty:
                                pass
                        
                        return True
                    time.sleep(0.1)
            
            logger.error(f"Connection failed after {self.MAX_RETRIES} attempts")
            return False
            
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            self.running = False
            return False
    
    def send_reliable(self, data):
        """Send data reliably over UDP"""
        if not self.connected:
            logger.error("Not connected")
            return False
            
        if isinstance(data, str):
            data = data.encode('utf-8')
            
        # Split data into chunks
        chunks = [data[i:i+self.DATA_SIZE] for i in range(0, len(data), self.DATA_SIZE)]
        total_chunks = len(chunks)
        
        for i, chunk in enumerate(chunks):
            seq_num = self.sequence_number
            self.sequence_number += 1
            
            # Set packet type
            packet_type = "LAST" if i == total_chunks - 1 else "DATA"
            
            # Try sending until acknowledged or max retries reached
            # UDP Client (ssh_udp_client.py) - continued

            # Try sending until acknowledged or max retries reached
            retries = 0
            ack_received = False
            
            while not ack_received and retries < self.MAX_RETRIES:
                # Send packet
                packet = self._create_packet(chunk, seq_num, packet_type)
                self.socket.sendto(packet, self.server_addr)
                
                # Wait for ACK
                try:
                    ack = self.ack_queue.get(timeout=self.TIMEOUT)
                    if ack == seq_num:
                        ack_received = True
                    else:
                        retries += 1
                except queue.Empty:
                    retries += 1
                    logger.warning(f"Timeout waiting for ACK {seq_num}, retry {retries}")
            
            if not ack_received:
                logger.error(f"Failed to send packet {seq_num} after {self.MAX_RETRIES} retries")
                return False
        
        return True
    
    def send_command(self, command):
        """Send command over SSH"""
        if not self.connected:
            logger.error("Not connected")
            return None
            
        try:
            start_time = time.time()
            
            # Send command
            logger.info(f"Sending command: {command}")
            self.send_reliable(command + "\n")
            
            # Wait for response
            response = b""
            response_timeout = time.time() + 2.0
            
            while time.time() < response_timeout:
                try:
                    if not self.data_queue.empty():
                        data = self.data_queue.get(timeout=0.5)
                        response += data
                        # Reset timeout when we get data
                        response_timeout = time.time() + 1.0
                except queue.Empty:
                    # No more data available
                    if response:
                        break
            
            execution_time = time.time() - start_time
            
            result = {
                'output': response.decode('utf-8'),
                'execution_time': execution_time
            }
            
            logger.info(f"Command executed in {execution_time:.2f} seconds")
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
            'file_transfer': None,
            'protocol': 'UDP',
            'data_sent': self.data_sent,
            'data_received': self.data_received
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
            
        # Update data metrics
        results['data_sent'] = self.data_sent
        results['data_received'] = self.data_received
        
        return results
    
    def disconnect(self):
        """Close SSH connection"""
        if self.connected:
            try:
                # Send exit command
                self.send_reliable("exit")
                time.sleep(0.5)  # Give server time to process
            except:
                pass
            
            # Stop receiver thread
            self.running = False
            if self.receiver_thread:
                self.receiver_thread.join(timeout=1.0)
            
            self.socket.close()
            self.connected = False
            logger.info("Connection closed")

def main():
    # Parse command line arguments
    host = '127.0.0.1'
    port = 2223
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
    client = SSHClientUDP(host, port, username, password)
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
            
            print(f"Total data sent: {results['data_sent']} bytes")
            print(f"Total data received: {results['data_received']} bytes")
            
            # Send a few interactive commands
            client.send_command("ls -la")
            client.send_command("pwd")
            client.send_command("exit")
            
        finally:
            client.disconnect()

if __name__ == "__main__":
    main()