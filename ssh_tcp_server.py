# TCP Server (ssh_tcp_server.py)
import socket
import threading
import paramiko
import sys
import os
import time
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Generate SSH host key
def get_host_key():
    key_file = 'server_key.pem'
    try:
        if os.path.exists(key_file):
            return paramiko.RSAKey(filename=key_file)
        else:
            # Generate new key
            key = paramiko.RSAKey.generate(2048)
            key.write_private_key_file(key_file)
            logger.info(f"Generated new server key: {key_file}")
            return key
    except Exception as e:
        logger.error(f"Error loading/generating host key: {str(e)}")
        # Generate in-memory key as fallback
        return paramiko.RSAKey.generate(2048)

class SSHServerInterface(paramiko.ServerInterface):
    def __init__(self):  # Fixed: Use double underscores for init
        self.event = threading.Event()
        self.channel = None

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        # For demo purposes, accept any username/password
        logger.info(f"Auth attempt: {username} with password")
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_publickey(self, username, key):
        logger.info(f"Auth attempt: {username} with key")
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username):
        return 'password,publickey'

    def check_channel_shell_request(self, channel):
        logger.info("Shell request received")
        self.channel = channel
        if channel:
            try:
                channel.settimeout(None)  # Disable timeouts
            except Exception as e:
                logger.error(f"Error setting channel timeout: {str(e)}")
        self.event.set()
        return True

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        logger.info(f"PTY request: {term}")
        return True

    def check_channel_exec_request(self, channel, command):
        logger.info(f"Execution request: {command.decode('utf-8')}")
        self.channel = channel
        if channel:
            try:
                channel.settimeout(None)  # Disable timeouts
            except Exception as e:
                logger.error(f"Error setting channel timeout: {str(e)}")
        self.event.set()
        return True

def handle_client(client_socket, client_address):
    transport = None
    channel = None
    
    try:
        start_time = time.time()
        logger.info(f"TCP connection from {client_address[0]}:{client_address[1]}")
        
        # Create transport
        transport = paramiko.Transport(client_socket)
        transport.local_version = "SSH-2.0-ParamikoSSHServer_0.1"  # Explicit version string
        
        # Set timeout for better error handling
        transport.banner_timeout = 60
        transport.handshake_timeout = 60
        
        # Add server key
        host_key = get_host_key()
        transport.add_server_key(host_key)
        
        # Start server
        server = SSHServerInterface()
        try:
            logger.info("Starting SSH server negotiation")
            transport.start_server(server=server)
        except paramiko.SSHException as e:
            logger.error(f"SSH negotiation failed: {str(e)}")
            return
        
        # Wait for auth
        logger.info("Waiting for authentication")
        channel = transport.accept(60)  # Increased timeout
        if channel is None:
            logger.warning("No channel established")
            return

        logger.info("Channel established, setting timeout to None")
        channel.settimeout(None)  # Critical: prevent timeouts during operation
        
        # Wait for client to request a shell or exec
        logger.info("Waiting for shell/exec request")
        server.event.wait(30)  # Increased timeout
        if not server.event.is_set():
            logger.warning("No shell/exec request received")
            # Continue anyway, as some clients may not explicitly request a shell
        
        # Send welcome message
        try:
            logger.info("Sending welcome message")
            channel.send(b"Welcome to SSH over TCP server!\r\n")
            channel.send(b"$ ")
        except Exception as e:
            logger.error(f"Error sending welcome message: {str(e)}")
            return
        
        # Create interactive shell session
        logger.info("Starting interactive shell")
        try:
            while True:
                try:
                    # Use longer timeout for recv to prevent quick exits
                    data = channel.recv(1024)
                    if not data:
                        logger.info("Client closed connection")
                        break
                    
                    if data.strip() == b'exit':
                        logger.info("Client sent exit command")
                        channel.send(b"Goodbye!\r\n")
                        break
                        
                    # Echo command
                    command_str = data.decode('utf-8', errors='replace').strip()
                    logger.info(f"Received command: {command_str}")
                    
                    # Execute command (simplified - just echo back for demo)
                    output = f"Executing: {command_str}\r\n"
                    channel.send(output.encode('utf-8'))
                    channel.send(b"$ ")
                except Exception as e:
                    logger.error(f"Error in command processing: {str(e)}")
                    break
        except Exception as e:
            logger.error(f"Channel error: {str(e)}")
        finally:
            logger.info("Interactive shell session ended")
        
    except Exception as e:
        logger.error(f"Error in client handler: {str(e)}")
    finally:
        try:
            if channel:
                channel.close()
        except:
            pass
        try:
            if transport:
                transport.close()
        except:
            pass
        try:
            client_socket.close()
        except:
            pass
        logger.info(f"Connection closed: {client_address[0]}:{client_address[1]}")
        session_time = time.time() - start_time
        logger.info(f"Session duration: {session_time:.2f} seconds")

def start_server(host, port):
    """Start the SSH TCP server"""
    # Create socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        # Try to bind with error handling for "address already in use"
        try:
            server_socket.bind((host, port))
        except OSError as e:
            if e.errno == 98:  # Address already in use
                logger.error(f"Port {port} is already in use. Try a different port.")
                return
            else:
                raise
                
        server_socket.listen(100)
        logger.info(f"SSH TCP server listening on {host}:{port}")
        
        while True:
            try:
                client, addr = server_socket.accept()
                client_thread = threading.Thread(target=handle_client, args=(client, addr))
                client_thread.daemon = True
                client_thread.start()
            except KeyboardInterrupt:
                logger.info("Server shutdown requested")
                break
            except Exception as e:
                logger.error(f"Error accepting connection: {str(e)}")
            
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
    finally:
        server_socket.close()
        logger.info("Server shutdown complete")

if __name__ == "__main__":
    # Parse command line arguments
    host = '127.0.0.1'
    port = 2222
    
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    
    # If port 2222 is in use, try another port
    try:
        start_server(host, port)
    except Exception as e:
        logger.error(f"Failed to start server on port {port}: {str(e)}")
        # Try alternative port
        alt_port = 2223
        logger.info(f"Attempting to start server on alternative port {alt_port}")
        try:
            start_server(host, alt_port)
        except Exception as e:
            logger.error(f"Failed to start server on alternative port {alt_port}: {str(e)}")