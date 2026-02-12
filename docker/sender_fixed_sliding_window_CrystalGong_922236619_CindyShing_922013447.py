#!/usr/bin/env python3
"""
Crystal Gong & Cindy Shing
ECS 152A - Computer Networks
Project 1: Fixed Sliding Window Protocol

This program implements a sliding window protocol for reliable UDP transmission.
"""

import socket
import time

# Network configuration
HOST = 'localhost'
PORT = 5001
MAX_PACKET = 1024
SEQ_SIZE = 4
DATA_SIZE = MAX_PACKET - SEQ_SIZE

# Protocol parameters
WINDOW = 100 # Maximum packets that can be unacknowledged
RETRANSMIT_TIME = 0.5 # Time before resending lost packets
INPUT_FILE = 'file.mp3'


def transmit_file():
    """
    Transmit the file using sliding window protocol and collect performance data.
    
    The sliding window allows us to send multiple packets before waiting for
    acknowledgments, which is much more efficient than stop-and-wait.
    
    Returns:
        tuple: (throughput in bytes/sec, average packet delay, performance score)
    """
    
    # Read input file into memory
    with open(INPUT_FILE, 'rb') as f:
        contents = f.read()
    
    total_bytes = len(contents)
    
    # Break file into packets with metadata
    # Each packet tracks whether it's been acknowledged and timing info
    packet_list = []
    position = 0
    
    while position < total_bytes:
        # Grab next chunk of data (up to DATA_SIZE bytes)
        data = contents[position:position + DATA_SIZE]
        sequence = position
        
        # Build packet with sequence number prefix
        raw_packet = int.to_bytes(sequence, SEQ_SIZE, signed=True, byteorder='big') + data
        
        # Store packet with tracking metadata
        packet_list.append({
            'sequence': sequence,
            'raw': raw_packet,
            'length': len(data),
            'is_acked': False,
            'first_sent': None, # Track when first transmitted (for delay calc)
            'recent_sent': None # Track most recent send (for timeout detection)
        })
        
        position += len(data)
    
    num_packets = len(packet_list)
    
    # Initialize UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', 0))  # Let OS assign us a port
    sock.settimeout(0.1)  # Non-blocking receive with short timeout
    
    # Record start time for throughput calculation
    begin = time.time()
    
    # Sliding window state variables
    left_edge = 0 # Index of oldest unacknowledged packet
    send_next = 0 # Index of next packet to transmit
    delays = [] # Store individual packet delays for averaging
    
    # Send initial burst of packets (fill the window)
    right_edge = min(left_edge + WINDOW, num_packets)
    for idx in range(send_next, right_edge):
        sock.sendto(packet_list[idx]['raw'], (HOST, PORT))
        packet_list[idx]['first_sent'] = time.time()
        packet_list[idx]['recent_sent'] = time.time()
    send_next = right_edge
    
    # Main transmission loop
    # Keep going until all packets are acknowledged
    last_check = time.time()
    total_acks = 0
    resends = 0
    
    while not all(p['is_acked'] for p in packet_list):
        
        # Try to receive an acknowledgment
        try:
            response, _ = sock.recvfrom(MAX_PACKET)
            total_acks += 1
            
            # Extract sequence number and message from ACK
            ack_seq = int.from_bytes(response[:SEQ_SIZE], signed=True, byteorder='big')
            ack_msg = response[SEQ_SIZE:].decode()
            
            # Process acknowledgment if valid
            if ack_msg == 'ack':
                # Mark all packets up to ack_seq as received (cumulative ACK)
                for idx in range(num_packets):
                    pkt = packet_list[idx]
                    next_expected = pkt['sequence'] + pkt['length']
                    
                    # If receiver has gotten past this packet, mark it done
                    if ack_seq >= next_expected and not pkt['is_acked']:
                        pkt['is_acked'] = True
                        
                        # Calculate delay from first send to now
                        if pkt['first_sent'] is not None:
                            elapsed = time.time() - pkt['first_sent']
                            delays.append(elapsed)
                
                # Slide window forward over acknowledged packets
                old_edge = left_edge
                while left_edge < num_packets and packet_list[left_edge]['is_acked']:
                    left_edge += 1
                
                # If window moved, send new packets that just entered
                if left_edge > old_edge:
                    # Make sure send_next is within the window
                    if send_next < left_edge:
                        send_next = left_edge
                    
                    # Send packets in the new window space
                    right_edge = min(left_edge + WINDOW, num_packets)
                    for idx in range(send_next, right_edge):
                        if not packet_list[idx]['is_acked']:
                            sock.sendto(packet_list[idx]['raw'], (HOST, PORT))
                            # Only set first_sent if this is the first transmission
                            if packet_list[idx]['first_sent'] is None:
                                packet_list[idx]['first_sent'] = time.time()
                            packet_list[idx]['recent_sent'] = time.time()
                    send_next = right_edge
        
        except socket.timeout:
            # No ACK received
            pass
        
        # Periodically check if any packets in window have timed out
        now = time.time()
        if now - last_check > 0.1:  # Check every 100ms
            right_edge = min(left_edge + WINDOW, num_packets)
            
            for idx in range(left_edge, right_edge):
                pkt = packet_list[idx]
                # If packet is unacked and hasn't been sent recently, resend it
                if not pkt['is_acked'] and pkt['recent_sent'] is not None:
                    if now - pkt['recent_sent'] > RETRANSMIT_TIME:
                        sock.sendto(pkt['raw'], (HOST, PORT))
                        pkt['recent_sent'] = now
                        resends += 1
            
            last_check = now
    
    # All data packets acknowledged - now send termination signal
    final_seq = total_bytes
    final_pkt = int.to_bytes(final_seq, SEQ_SIZE, signed=True, byteorder='big') + b''
    
    # Wait for final ACK and FIN from receiver
    got_fin = False
    while not got_fin:
        try:
            sock.sendto(final_pkt, (HOST, PORT))
            
            # Get ACK for empty packet
            response, _ = sock.recvfrom(MAX_PACKET)
            ack_seq = int.from_bytes(response[:SEQ_SIZE], signed=True, byteorder='big')
            ack_msg = response[SEQ_SIZE:].decode()
            
            # Once we get the right ACK, wait for FIN
            if ack_msg == 'ack' and ack_seq == final_seq:
                fin_response, _ = sock.recvfrom(MAX_PACKET)
                fin_msg = fin_response[SEQ_SIZE:].decode()
                
                if fin_msg == 'fin':
                    got_fin = True
        
        except socket.timeout:
            continue
    
    # Send final acknowledgment to close connection cleanly
    closing = int.to_bytes(0, SEQ_SIZE, signed=True, byteorder='big') + b'==FINACK=='
    sock.sendto(closing, (HOST, PORT))
    
    # Record end time
    finish = time.time()
    sock.close()
    
    # Calculate performance metrics
    duration = finish - begin
    rate = total_bytes / duration  # Bytes per second
    mean_delay = sum(delays) / len(delays) if delays else 0  # Average seconds per packet
    
    # Compute overall performance score using provided formula
    score = 0.3 * (rate / 1000) + 0.7 / mean_delay if mean_delay > 0 else 0
    
    return rate, mean_delay, score


def main():
    """
    Execute the sliding window protocol for the specified number of iterations
    and output the averaged results.
    """
    
    # Storage for results across multiple runs
    throughput_results = []
    delay_results = []
    metric_results = []
    
    # Run the protocol multiple times to account for network variability
    runs = 10  # Change to 10 for final submission !!!
    
    for run in range(runs):
        rate, delay, metric = transmit_file()
        
        throughput_results.append(rate)
        delay_results.append(delay)
        metric_results.append(metric)
    
    # Calculate averages across all runs
    avg_rate = sum(throughput_results) / len(throughput_results)
    avg_delay = sum(delay_results) / len(delay_results)
    avg_metric = sum(metric_results) / len(metric_results)
    
    # Output results in required format
    # Three lines with exactly 7 decimal places, no labels
    print(f"{avg_rate:.7f}")
    print(f"{avg_delay:.7f}")
    print(f"{avg_metric:.7f}")


if __name__ == "__main__":
    main()