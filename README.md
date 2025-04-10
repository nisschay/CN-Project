# TCP vs UDP SSH Implementation Comparison

College project comparing SSH performance over TCP and UDP transport protocols.

## Project Structure

```
├── ssh_benchmark_results.json
├── ssh_compare.py
├── ssh_comparison_report.txt
├── ssh_protocol_comparison.png
├── ssh_tcp_client.py
├── ssh_tcp_server.py
├── ssh_udp_client.py
└── ssh_udp_server.py
```

## Overview

This project implements SSH over both TCP and UDP to benchmark performance differences. Key metrics include connection time, command execution speed, file transfer throughput, and protocol overhead.

## Requirements

```
matplotlib
pandas
numpy
```

## Usage

Run the complete benchmark:
```bash
python ssh_compare.py
```

The script:
- Starts both server implementations if not running
- Runs benchmark battery on both protocols
- Generates comparison graph as PNG
- Saves metrics to JSON
- Creates analysis report as TXT

## Implementation Details

The benchmark performs:
1. Connection time measurement
2. Command execution tests (10 commands by default)
3. File transfer tests (1KB, 10KB, 100KB)
4. Protocol overhead calculation

Servers run on localhost:
- TCP: Port 2222
- UDP: Port 2223

## Output

The benchmark generates:
- Visual performance comparison (`ssh_protocol_comparison.png`)
- Raw metrics (`ssh_benchmark_results.json`)
- Analysis report with recommendations (`ssh_comparison_report.txt`)