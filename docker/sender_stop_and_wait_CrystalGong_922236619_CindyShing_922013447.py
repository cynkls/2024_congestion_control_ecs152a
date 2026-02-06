#!/usr/bin/env python3
"""
Crystal Gong & Cindy Shing
ECS 152A; Project 1
Stop-and-Wait Implementation
"""

'''
Stop-and-Wait: 
1. Send one packet
2. Wait for ACK
3. Send next packet
'''

# ------IMPORTS------
import socket
import time
import sys

# ------NAMED CONSTANTS------
# From receiver.py
PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MESSAGE_SIZE = PACKET_SIZE - SEQ_ID_SIZE
# Other
RECEIVER_IP = 'localhost' 
RECEIVER_PORT = 5001 # From receiver.py's socket
ACK_TIMEOUT = 0.5 # Maybe change to 1.0s before submitting
FILE_TO_SEND = 'file.mp3'


def send_one_packet(sock, packet_data, seq_num, packet_num):
    """
    Send one packet, then wait for its ACK from the receiver.
    If no ACK is received, keep retransmitting the same packet until the ACK is received.

    Args:
        sock: The UDP socket
        packet_data: The data chunk to send (up to 1020 bytes = MESSAGE_SIZE)
        seq_num: Sequence number (byte position in file)
        packet_num: Which packet number this is (for debugging)
    
    Returns:
        Time it took from (first send -> receiving ACK)
    """

    # Build the packet
    # Converts integer (sequence number) to raw bytes; networks can only send bytes (raw binary)
    packet = int.to_bytes(seq_num, SEQ_ID_SIZE, signed=True, byteorder='big') + packet_data
    
    # Variables
    received_ack = False
    start_time = time.time() # Start timer right when the sender first tries to send
    num_attempts = 0 # Number of times the sender has tried to send the packet
    
    while not received_ack:
        try:
            # Send the packet
            sock.sendto(packet, (RECEIVER_IP, RECEIVER_PORT))
            num_attempts += 1
            
            # ------DEBUG START------
            # Print progress for first 3 packets and every 500 packets
            if packet_num < 3 or packet_num % 500 == 0:
                print(f"Packet {packet_num}: seq_num={seq_num}, data_size={len(packet_data)}, attempt={num_attempts}", file=sys.stderr)
            # ------DEBUG END------
            
            # Wait for ACK (automatically times out if no ACK is received)
            # sock.recvfrom() blocks until data arrives OR timeout occurs
            # ack_packet = data
            ack_packet, _ = sock.recvfrom(PACKET_SIZE)
            
            # Parse the ACK packet that was received
            ack_seq_num = int.from_bytes(ack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big') # Sequence number (4 bytes)
            ack_text = ack_packet[SEQ_ID_SIZE:].decode() # Actual message (3 bytes)

            # ------DEBUG START------
            # Print details for first 3 packets
            if packet_num < 3:
                print(f"  Got ACK: seq_num={ack_seq_num}, message='{ack_text}', need>={seq_num + len(packet_data)}", file=sys.stderr)
            # ------DEBUG END------
            
            # Check if the ACK is for the current packet
            # Receiver uses cumulative ACK (ACK = next byte it wants)
            # Thus ACK should be >= current sequence length + current data length
            if ((ack_text == 'ack') and (ack_seq_num >= (seq_num + len(packet_data)))): # Why >= ? 
                received_ack = True
                end_time = time.time() # 'Stop the timer'
                delay = end_time - start_time
                
                if packet_num < 3:
                    print(f"  ✓ ACK accepted! Delay: {delay:.4f}s", file=sys.stderr)
                
                return delay
            
            # ------DEBUG START------
            # else:
                # print(f"✗ ACK rejected - not the right one", file=sys.stderr)
            # ------DEBUG END------
                    
        except socket.timeout:
            # Didn't get ACK in time, so retry it!
            # ------DEBUG START------
            print(f"TIMEOUT on packet {packet_num}, retrying...", file=sys.stderr)
            # ------DEBUG END------
            continue


def send_file():
    """
    Main function: Send the entire file using stop-and-wait protocol.
    
    Returns: (3 requirements)
        throughput: bytes per second
        avg_delay: average seconds per packet
        performance_metric: performance metric
    """
    
    # Set up the socket 
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP socket
    sock.bind(('', 0)) # Bind to any available port, other than the receiver (5001)
    sock.settimeout(ACK_TIMEOUT) # Timeout duration
    
    overall_start = time.time()  # Start timer for throughput calculation
    
    # Read the file
    with open(FILE_TO_SEND, 'rb') as f:
        file_contents = f.read()
    file_size = len(file_contents)
    
    # Send all the packets
    all_delays = []  # Track delay for each packet
    current_position = 0 # Current position/offset in file
    packet_count = 0 # Total number of packets sent
    
    # ------DEBUG START------
    print("Starting to send packets...", file=sys.stderr)
    # ------DEBUG END------
    
    # Parse through file
    while current_position < file_size:
        # Get the next chunk of data (up to 1020 bytes)
        data_chunk = file_contents[current_position:current_position + MESSAGE_SIZE]
        
        # Sequence number = byte position in the file
        seq_number = current_position
        
        # Send current packet and wait for ACK
        packet_delay = send_one_packet(sock, data_chunk, seq_number, packet_count)
        all_delays.append(packet_delay)
        
        # Move to next chunk
        current_position += len(data_chunk)
        packet_count += 1
    
    # ------DEBUG START------
    print(f"All {packet_count} packets sent successfully!", file=sys.stderr)
    # ------DEBUG END------
    
    # Send termination signal (empty packet) when finished
    # ------DEBUG START------
    print("Sending termination signal...", file=sys.stderr)
    # ------DEBUG END------
    final_seq_num = current_position
    empty_packet = int.to_bytes(final_seq_num, SEQ_ID_SIZE, signed=True, byteorder='big') + b'' # b'' = empty bytes
    
    # Wait for final ACK and FIN message
    received_fin = False
    while not received_fin:
        try:
            sock.sendto(empty_packet, (RECEIVER_IP, RECEIVER_PORT))
            
            # Get ACK for empty packet
            ack_packet, _ = sock.recvfrom(PACKET_SIZE)
            ack_seq = int.from_bytes(ack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')
            ack_msg = ack_packet[SEQ_ID_SIZE:].decode()
            
            if ((ack_msg == 'ack') and (ack_seq == final_seq_num)):
                # Get FIN message
                fin_packet, _ = sock.recvfrom(PACKET_SIZE)
                fin_seq = int.from_bytes(fin_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')
                fin_msg = fin_packet[SEQ_ID_SIZE:].decode()
                
                if fin_msg == 'fin':
                    received_fin = True
                    # ------DEBUG START------
                    print("Received FIN from receiver", file=sys.stderr)
                    # ------DEBUG END------
                    
        except socket.timeout:
            continue
    
    # Send FINACK (final acknowledgement) to tell receiver FIN has been received
    finack = int.to_bytes(0, SEQ_ID_SIZE, signed=True, byteorder='big') + b'==FINACK=='
    sock.sendto(finack, (RECEIVER_IP, RECEIVER_PORT))
    # ------DEBUG START------
    print("Sent FINACK - connection closed", file=sys.stderr)
    # ------DEBUG END------
    
    overall_end = time.time()
    sock.close()
    
    # Calculate necessary metrics
    total_time = overall_end - overall_start # Total time taken
    throughput = file_size / total_time  # Bytes sent per second
    avg_delay = sum(all_delays) / len(all_delays) # Average seconds per packet
    performance_metric = 0.3 * (throughput / 1000) + 0.7 / avg_delay # Performance metric formula on project details doc
    
    # ------DEBUG START------
    print(f"\nCompleted in {total_time:.2f}s", file=sys.stderr)
    print(f"Throughput: {throughput:.2f} bytes/s", file=sys.stderr)
    print(f"Avg delay per packet: {avg_delay:.4f}s", file=sys.stderr)
    print(f"Performance metric: {performance_metric:.4f}", file=sys.stderr)
    # ------DEBUG END------
    
    return (throughput, avg_delay, performance_metric)


def main():
    """
    Run the file transfer 10 times and average the results.
    """

    all_throughputs = []
    all_delays = []
    all_metrics = []
    
    num_iterations = 1 # Change to 1 for testing; should be 10
    
    for iteration in range(num_iterations):
        # ------DEBUG START------
        print(f"\n{'='*50}", file=sys.stderr)
        print(f"ITERATION {iteration + 1} of {num_iterations}", file=sys.stderr)
        print(f"{'='*50}", file=sys.stderr)
        # ------DEBUG END------
        
        throughput, delay, metric = send_file()
        
        all_throughputs.append(throughput)
        all_delays.append(delay)
        all_metrics.append(metric)
    
    # Calculate averages across all iterations
    avg_throughput = sum(all_throughputs) / len(all_throughputs)
    avg_delay = sum(all_delays) / len(all_delays)
    avg_metric = sum(all_metrics) / len(all_metrics)
    
    # Output final results
    # Exactly 3 lines, rounded 7 decimal points per project specs
    print(f"{avg_throughput:.7f}")
    print(f"{avg_delay:.7f}")
    print(f"{avg_metric:.7f}")


if __name__ == "__main__":
    main()