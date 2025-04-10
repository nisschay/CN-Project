# UDP Server (ssh_udp_server.py)
import socket
import threading
import sys
import time
import logging
import json
import hashlib
import os
import queue
import paramiko
from io import StringIO

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Generate SSH host key if it doesn't exist
if not os.path.exists('server_key.pem'):
    key = paramiko.RSAKey.generate(2048)
    key.write_private_key_file('server_key.pem')
    logger.info("Generated new server key: server_key.pem")

host_key = paramiko.RSAKey(filename='server_key.pem')

class ReliableUDPServer:
    """Reliable UDP transport layer for SSH server"""
    
    PACKET_SIZE = 1400
    HEADER_SIZE = 200
    DATA_SIZE = PACKET_SIZE - HEADER_SIZE
    TIMEOUT = 1.0
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.clients = {}  # Store client session info
        self.sequence_numbers = {}  # Track sequence numbers per client
        self.running = False
        
    def _create_packet(self, data, seq_num, packet_type="DATA", session_id=""):
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
            'session': session_id
        }).encode('utf-8')
        
        # Pad header to fixed size
        header = header.ljust(self.HEADER_SIZE, b' ')
        
        # Combine header and data
        packet = header + data
        return packet
    
    def _parse_packet(self, packet):
        """Parse received packet into header and data"""
        header = packet[:self.HEADER_SIZE].strip()
        data = packet[self.HEADER_SIZE:]
        
        try:
            header_info = json.loads(header.decode('utf-8'))
            
            # Verify checksum for data packets
            if header_info['type'] not in ["ACK", "CONNECT"]:
                calculated_checksum = hashlib.md5(data).hexdigest()
                if header_info['checksum'] != calculated_checksum:
                    logger.warning(f"Checksum mismatch for packet {header_info['seq']}")
                    return None
                    
            return {
                'seq': header_info['seq'],
                'type': header_info['type'],
                'length': header_info['length'],
                'session': header_info.get('session', ""),
                'data': data[:header_info['length']] if 'length' in header_info else data
            }
        except Exception as e:
            logger.error(f"Error parsing packet: {str(e)}")
            return None
    
    def _send_ack(self, seq_num, addr, session_id=""):
        """Send acknowledgment packet"""
        ack_packet = self._create_packet(b"ACK", seq_num, packet_type="ACK", session_id=session_id)
        self.socket.sendto(ack_packet, addr)
    
    def send_data(self, data, addr, session_id):
        """Send data to client"""
        if isinstance(data, str):
            data = data.encode('utf-8')
            
        # Get sequence number for this client session
        if session_id not in self.sequence_numbers:
            self.sequence_numbers[session_id] = 0
        seq_num = self.sequence_numbers[session_id]
        self.sequence_numbers[session_id] += 1
        
        # Split data into chunks
        chunks = [data[i:i+self.DATA_SIZE] for i in range(0, len(data), self.DATA_SIZE)]
        total_chunks = len(chunks)
        
        for i, chunk in enumerate(chunks):
            packet_type = "LAST" if i == total_chunks - 1 else "DATA"
            packet = self._create_packet(chunk, seq_num + i, packet_type, session_id)
            
            # Send with retries
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    self.socket.sendto(packet, addr)
                    # For simplicity, we're not waiting for ACKs in this demo
                    # In a real implementation, we would wait for ACKs
                    break
                except Exception as e:
                    logger.error(f"Error sending packet: {str(e)}")
                    if attempt == max_retries - 1:
                        return False
                    time.sleep(0.1)
        
        # Update sequence number
        self.sequence_numbers[session_id] += total_chunks
        return True
    
    def handle_client(self, session_id, addr):
        """Handle SSH session for a connected client"""
        logger.info(f"New SSH session {session_id} from {addr[0]}:{addr[1]}")
        
        # Send welcome message
        welcome = "Welcome to SSH over UDP server!\r\n$ "
        self.send_data(welcome, addr, session_id)
        
        # Handle commands (simplified for demo)
        client_info = self.clients[session_id]
        buffer = client_info['buffer']
        
        while session_id in self.clients:
            # Process commands in buffer
            while not buffer.empty():
                try:
                    cmd_data = buffer.get(block=False)
                    cmd = cmd_data.decode('utf-8').strip()
                    
                    if cmd.lower() == 'exit':
                        logger.info(f"Client requested exit: {session_id}")
                        self.send_data("Goodbye!\r\n", addr, session_id)
                        del self.clients[session_id]
                        return
                    
                    # Execute command (simplified)
                    logger.info(f"Executing command: {cmd}")
                    output = f"Executing: {cmd}\r\n$ "
                    self.send_data(output, addr, session_id)
                    
                except queue.Empty:
                    break
                except Exception as e:
                    logger.error(f"Error processing command: {str(e)}")
            
            time.sleep(0.1)  # Prevent CPU hogging
    
    def start(self):
        """Start the UDP server"""
        self.running = True
        logger.info(f"SSH UDP server listening on {self.host}:{self.port}")
        
        try:
            while self.running:
                try:
                    # Set timeout to allow for clean shutdown
                    self.socket.settimeout(1.0)
                    data, addr = self.socket.recvfrom(self.PACKET_SIZE)
                    self.socket.settimeout(None)
                    
                    packet = self._parse_packet(data)
                    if not packet:
                        continue
                    
                    session_id = packet['session']
                    
                    # Handle different packet types
                    if packet['type'] == "CONNECT":
                        # New connection request
                        if session_id not in self.clients:
                            # Generate new session ID if not provided
                            if not session_id:
                                session_id = hashlib.md5(f"{addr[0]}:{addr[1]}:{time.time()}".encode()).hexdigest()
                            
                            # Create new client session
                            self.clients[session_id] = {
                                'addr': addr,
                                'last_active': time.time(),
                                'buffer': queue.Queue()
                            }
                            
                            # Initialize sequence number
                            self.sequence_numbers[session_id] = 0
                            
                            # Send connection acknowledgment
                            ack_packet = self._create_packet(session_id.encode('utf-8'), 0, 
                                                           "CONNECT_ACK", session_id)
                            self.socket.sendto(ack_packet, addr)
                            
                            # Start session handler
                            client_thread = threading.Thread(
                                target=self.handle_client,
                                args=(session_id, addr)
                            )
                            client_thread.daemon = True
                            client_thread.start()
                            
                            logger.info(f"New client connected: {session_id} from {addr[0]}:{addr[1]}")
                        else:
                            # Resend connection acknowledgment
                            ack_packet = self._create_packet(session_id.encode('utf-8'), 0, 
                                                           "CONNECT_ACK", session_id)
                            self.socket.sendto(ack_packet, addr)
                    
                    elif packet['type'] in ["DATA", "LAST"]:
                        # Data packet
                        if session_id in self.clients:
                            # Update last active time
                            self.clients[session_id]['last_active'] = time.time()
                            
                            # Send acknowledgment
                            self._send_ack(packet['seq'], addr, session_id)
                            
                            # Process data
                            self.clients[session_id]['buffer'].put(packet['data'])
                            
                            logger.debug(f"Received data packet {packet['seq']} for session {session_id}")
                        else:
                            logger.warning(f"Received data for unknown session: {session_id}")
                    
                except socket.timeout:
                    pass
                except Exception as e:
                    logger.error(f"Error in server loop: {str(e)}")
                    
                # Clean up inactive sessions
                current_time = time.time()
                inactive_sessions = []
                for sess_id, info in self.clients.items():
                    if current_time - info['last_active'] > 60:  # 60 seconds timeout
                        inactive_sessions.append(sess_id)
                
                for sess_id in inactive_sessions:
                    logger.info(f"Removing inactive session: {sess_id}")
                    del self.clients[sess_id]
                    
        except KeyboardInterrupt:
            logger.info("Server shutting down...")
        finally:
            self.socket.close()
            self.running = False

def start_server(host, port):
    """Start the SSH UDP server"""
    server = ReliableUDPServer(host, port)
    server.start()

if __name__ == "__main__":
    # Parse command line arguments
    host = '127.0.0.1'
    port = 2223
    
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    
    start_server(host, port)


