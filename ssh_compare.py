# ssh_compare.py - Compare TCP and UDP implementations
import sys
import time
import subprocess
import json
import os
import socket  # Add this missing import
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import logging
from concurrent.futures import ThreadPoolExecutor
from ssh_tcp_client import SSHClientTCP
from ssh_udp_client import SSHClientUDP

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def ensure_servers_running(tcp_port, udp_port):
    """Make sure the TCP and UDP servers are running"""
    # Check if TCP server is running
    try:
        with socket.create_connection(('127.0.0.1', tcp_port), timeout=1):
            logger.info(f"TCP server already running on port {tcp_port}")
    except:
        logger.info(f"Starting TCP server on port {tcp_port}")
        subprocess.Popen([sys.executable, 'ssh_tcp_server.py', '127.0.0.1', str(tcp_port)])
        time.sleep(2)  # Give server time to start
    
    # For UDP, we can't easily check if server is running, so just start it
    # and let it handle the case if it's already running
    logger.info(f"Starting UDP server on port {udp_port}")
    subprocess.Popen([sys.executable, 'ssh_udp_server.py', '127.0.0.1', str(udp_port)])
    time.sleep(2)  # Give server time to start

def run_benchmark(protocol, host, port, username, password, num_commands=10, file_sizes=None):
    """Run benchmark for the specified protocol"""
    if file_sizes is None:
        file_sizes = [1024, 1024*10, 1024*100]  # Default file sizes
    
    results = {
        'protocol': protocol,
        'connection_time': 0,
        'command_times': [],
        'file_transfers': [],
        'data_sent': 0,
        'data_received': 0
    }
    
    try:
        if protocol.upper() == 'TCP':
            client = SSHClientTCP(host, port, username, password)
        else:  # UDP
            client = SSHClientUDP(host, port, username, password)
        
        # Connect
        if client.connect():
            results['connection_time'] = client.connection_time
            
            # Run command benchmark
            for i in range(num_commands):
                command = f"echo This is test command {i}"
                result = client.send_command(command)
                if result:
                    results['command_times'].append(result['execution_time'])
            
            # Run file transfer benchmark for different file sizes
            for size in file_sizes:
                content = "X" * size
                transfer_result = client.send_file(content, f"test_file_{size}.txt")
                if transfer_result:
                    results['file_transfers'].append({
                        'size': size,
                        'time': transfer_result['transfer_time'],
                        'speed': transfer_result['speed']
                    })
            
            # Get data metrics
            if hasattr(client, 'data_sent'):
                results['data_sent'] = client.data_sent
            if hasattr(client, 'data_received'):
                results['data_received'] = client.data_received
                
            # Disconnect
            client.disconnect()
            
        return results
        
    except Exception as e:
        logger.error(f"Benchmark error with {protocol}: {str(e)}")
        return results

def plot_results(tcp_results, udp_results):
    """Create plots comparing TCP and UDP performance"""
    
    # Make sure we have matplotlib and pandas
    try:
        import matplotlib.pyplot as plt
        import pandas as pd
        import numpy as np
    except ImportError:
        print("Please install matplotlib, pandas, and numpy to generate plots:")
        print("pip install matplotlib pandas numpy")
        return
    
    # Set up the figure for subplots
    plt.figure(figsize=(15, 10))
    
    # 1. Connection Time Comparison
    plt.subplot(2, 3, 1)
    protocols = ['TCP', 'UDP']
    conn_times = [tcp_results['connection_time'], udp_results['connection_time']]
    plt.bar(protocols, conn_times, color=['blue', 'orange'])
    plt.title('Connection Time (lower is better)')
    plt.ylabel('Time (seconds)')
    
    # 2. Average Command Execution Time
    plt.subplot(2, 3, 2)
    if tcp_results['command_times'] and udp_results['command_times']:
        avg_cmd_time_tcp = sum(tcp_results['command_times']) / len(tcp_results['command_times'])
        avg_cmd_time_udp = sum(udp_results['command_times']) / len(udp_results['command_times'])
        
        plt.bar(protocols, [avg_cmd_time_tcp, avg_cmd_time_udp], color=['blue', 'orange'])
        plt.title('Avg Command Execution Time (lower is better)')
        plt.ylabel('Time (seconds)')
    
    # 3. File Transfer Speeds for Different Sizes
    plt.subplot(2, 3, 3)
    
    # Extract file sizes and speeds
    tcp_sizes = [ft['size'] for ft in tcp_results['file_transfers']]
    tcp_speeds = [ft['speed'] for ft in tcp_results['file_transfers']]
    
    udp_sizes = [ft['size'] for ft in udp_results['file_transfers']]
    udp_speeds = [ft['speed'] for ft in udp_results['file_transfers']]
    
    # Create DataFrame for plotting
    if tcp_sizes and udp_sizes:
        # Combine data
        df = pd.DataFrame({
            'Size': tcp_sizes + udp_sizes,
            'Speed': tcp_speeds + udp_speeds,
            'Protocol': ['TCP'] * len(tcp_sizes) + ['UDP'] * len(udp_sizes)
        })
        
        # Plot grouped bar chart
        sizes = sorted(list(set(tcp_sizes).union(set(udp_sizes))))
        x = np.arange(len(sizes))
        width = 0.35
        
        tcp_speeds_by_size = [next((ft['speed'] for ft in tcp_results['file_transfers'] 
                              if ft['size'] == size), 0) for size in sizes]
        udp_speeds_by_size = [next((ft['speed'] for ft in udp_results['file_transfers'] 
                              if ft['size'] == size), 0) for size in sizes]
        
        plt.bar(x - width/2, tcp_speeds_by_size, width, label='TCP')
        plt.bar(x + width/2, udp_speeds_by_size, width, label='UDP')
        
        plt.xlabel('File Size (bytes)')
        plt.ylabel('Speed (bytes/sec)')
        plt.title('File Transfer Speed (higher is better)')
        plt.xticks(x, [f"{size/1024:.0f}KB" for size in sizes])
        plt.legend()
    
    # 4. Command Execution Time Distribution
    plt.subplot(2, 3, 4)
    if tcp_results['command_times'] and udp_results['command_times']:
        plt.boxplot([tcp_results['command_times'], udp_results['command_times']], labels=['TCP', 'UDP'])
        plt.title('Command Execution Time Distribution')
        plt.ylabel('Time (seconds)')
    
    # 5. Data Sent/Received
    plt.subplot(2, 3, 5)
    data_metrics = {
        'Sent': [tcp_results['data_sent'], udp_results['data_sent']],
        'Received': [tcp_results['data_received'], udp_results['data_received']]
    }
    
    df = pd.DataFrame(data_metrics, index=['TCP', 'UDP'])
    df.plot(kind='bar', ax=plt.gca())
    plt.title('Data Transfer Volume')
    plt.ylabel('Bytes')
    
    # 6. Protocol Efficiency (bytes received per second)
    plt.subplot(2, 3, 6)
    total_time_tcp = tcp_results['connection_time'] + sum(tcp_results['command_times']) + \
                    sum(ft['time'] for ft in tcp_results['file_transfers'])
    total_time_udp = udp_results['connection_time'] + sum(udp_results['command_times']) + \
                    sum(ft['time'] for ft in udp_results['file_transfers'])
    
    efficiency_tcp = tcp_results['data_received'] / total_time_tcp if total_time_tcp > 0 else 0
    efficiency_udp = udp_results['data_received'] / total_time_udp if total_time_udp > 0 else 0
    
    plt.bar(protocols, [efficiency_tcp, efficiency_udp], color=['blue', 'orange'])
    plt.title('Protocol Efficiency')
    plt.ylabel('Bytes received per second')
    
    # Save and show plots
    plt.tight_layout()
    plt.savefig('ssh_protocol_comparison.png')
    plt.close()
    
    print(f"Plots saved to ssh_protocol_comparison.png")

def save_results(tcp_results, udp_results):
    """Save benchmark results to file"""
    results = {
        'tcp': tcp_results,
        'udp': udp_results,
        'timestamp': time.time()
    }
    
    with open('ssh_benchmark_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to ssh_benchmark_results.json")

def generate_report(tcp_results, udp_results):
    """Generate a text report of the results"""
    report = "SSH Protocol Comparison Report\n"
    report += "==========================\n\n"
    
    # Connection time
    report += "Connection Time:\n"
    report += f"  TCP: {tcp_results['connection_time']:.4f} seconds\n"
    report += f"  UDP: {udp_results['connection_time']:.4f} seconds\n"
    report += f"  Winner: {'TCP' if tcp_results['connection_time'] < udp_results['connection_time'] else 'UDP'}\n\n"
    
    # Command execution
    if tcp_results['command_times'] and udp_results['command_times']:
        avg_tcp = sum(tcp_results['command_times']) / len(tcp_results['command_times'])
        avg_udp = sum(udp_results['command_times']) / len(udp_results['command_times'])
        
        report += "Command Execution Time (average):\n"
        report += f"  TCP: {avg_tcp:.4f} seconds\n"
        report += f"  UDP: {avg_udp:.4f} seconds\n"
        report += f"  Winner: {'TCP' if avg_tcp < avg_udp else 'UDP'}\n\n"
    
    # File transfer
    if tcp_results['file_transfers'] and udp_results['file_transfers']:
        report += "File Transfer Performance:\n"
        
        # Get all unique file sizes
        all_sizes = sorted(list(set([ft['size'] for ft in tcp_results['file_transfers']] + 
                              [ft['size'] for ft in udp_results['file_transfers']])))
        
        for size in all_sizes:
            tcp_ft = next((ft for ft in tcp_results['file_transfers'] if ft['size'] == size), None)
            udp_ft = next((ft for ft in udp_results['file_transfers'] if ft['size'] == size), None)
            
            report += f"  File Size: {size/1024:.1f} KB\n"
            
            if tcp_ft:
                report += f"    TCP: {tcp_ft['speed']:.2f} bytes/sec ({tcp_ft['time']:.4f} sec)\n"
            
            if udp_ft:
                report += f"    UDP: {udp_ft['speed']:.2f} bytes/sec ({udp_ft['time']:.4f} sec)\n"
            
            if tcp_ft and udp_ft:
                winner = 'TCP' if tcp_ft['speed'] > udp_ft['speed'] else 'UDP'
                report += f"    Winner: {winner}\n"
            
            report += "\n"
    
    # Data efficiency
    report += "Data Transfer Efficiency:\n"
    report += f"  TCP: Sent {tcp_results['data_sent']} bytes, Received {tcp_results['data_received']} bytes\n"
    report += f"  UDP: Sent {udp_results['data_sent']} bytes, Received {udp_results['data_received']} bytes\n"
    
    # Protocol overhead (bytes sent / bytes received)
    tcp_overhead = tcp_results['data_sent'] / tcp_results['data_received'] if tcp_results['data_received'] > 0 else 0
    udp_overhead = udp_results['data_sent'] / udp_results['data_received'] if udp_results['data_received'] > 0 else 0
    
    report += f"  TCP Overhead Ratio: {tcp_overhead:.2f}\n"
    report += f"  UDP Overhead Ratio: {udp_overhead:.2f}\n"
    report += f"  Winner (lower is better): {'TCP' if tcp_overhead < udp_overhead else 'UDP'}\n\n"
    
    # Overall recommendation
    tcp_points = 0
    udp_points = 0
    
    # Connection time
    if tcp_results['connection_time'] < udp_results['connection_time']:
        tcp_points += 1
    else:
        udp_points += 1
    
    # Command execution
    if tcp_results['command_times'] and udp_results['command_times']:
        avg_tcp = sum(tcp_results['command_times']) / len(tcp_results['command_times'])
        avg_udp = sum(udp_results['command_times']) / len(udp_results['command_times'])
        
        if avg_tcp < avg_udp:
            tcp_points += 1
        else:
            udp_points += 1
    
    # File transfer (average across all sizes)
    if tcp_results['file_transfers'] and udp_results['file_transfers']:
        avg_tcp_speed = sum(ft['speed'] for ft in tcp_results['file_transfers']) / len(tcp_results['file_transfers'])
        avg_udp_speed = sum(ft['speed'] for ft in udp_results['file_transfers']) / len(udp_results['file_transfers'])
        
        if avg_tcp_speed > avg_udp_speed:
            tcp_points += 1
        else:
            udp_points += 1
    
    # Overhead
    if tcp_overhead < udp_overhead:
        tcp_points += 1
    else:
        udp_points += 1
    
    # Overall recommendation
    report += "Overall Recommendation:\n"
    if tcp_points > udp_points:
        report += "  TCP is recommended for SSH implementation based on the benchmark results.\n"
        report += f"  Score: TCP {tcp_points}, UDP {udp_points}\n\n"
    elif udp_points > tcp_points:
        report += "  UDP is recommended for SSH implementation based on the benchmark results.\n"
        report += f"  Score: UDP {udp_points}, TCP {tcp_points}\n\n"
    else:
        report += "  Both protocols performed similarly overall. Consider your specific use case:\n"
        report += "  - Use TCP for reliable connections and standard compatibility\n"
        report += "  - Use UDP where minimizing latency is critical and packet loss is acceptable\n\n"
    
    # Protocol-specific observations
    report += "Protocol-Specific Observations:\n"
    report += "  TCP:\n"
    report += "  - Connection-oriented, reliable by design\n"
    report += "  - Standard protocol for SSH, widely compatible\n"
    report += "  - Better flow control and congestion handling\n"
    report += "  - More overhead for connection establishment\n\n"
    
    report += "  UDP:\n"
    report += "  - Connectionless, requires custom reliability mechanisms\n"
    report += "  - Non-standard for SSH, limited compatibility\n"
    report += "  - Potentially lower latency for small packets\n"
    report += "  - More prone to packet loss\n"
    
    # Save report to file
    with open('ssh_comparison_report.txt', 'w') as f:
        f.write(report)
    
    print(f"Report saved to ssh_comparison_report.txt")
    return report

def main():
    # Default settings
    host = '127.0.0.1'
    tcp_port = 2222
    udp_port = 2223
    username = 'test'
    password = 'test'
    num_commands = 10
    file_sizes = [1024, 1024*10, 1024*100]  # 1KB, 10KB, 100KB
    
    # Ensure servers are running
    ensure_servers_running(tcp_port, udp_port)
    
    # Run TCP benchmark
    print("Running TCP benchmark...")
    tcp_results = run_benchmark('TCP', host, tcp_port, username, password, num_commands, file_sizes)
    
    # Run UDP benchmark
    print("Running UDP benchmark...")
    udp_results = run_benchmark('UDP', host, udp_port, username, password, num_commands, file_sizes)
    
    # Save results
    save_results(tcp_results, udp_results)
    
    # Generate plots
    plot_results(tcp_results, udp_results)
    
    # Generate and print report
    report = generate_report(tcp_results, udp_results)
    print("\nComparison Report:")
    print("================")
    print(report)

if __name__ == "__main__":
    main()