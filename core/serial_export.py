"""Serial export module for sending pixel matrix to ESP32 via UART.

Optimized Protocol (fixed 64x64):
- Header: 4 bytes magic (0xBC, 0xD1, 0x32, 0x57)
- Data: 8192 bytes (64x64 RGB565, row-major, little-endian)
- Checksum: 2 bytes (sum of all data bytes, uint16 LE)
"""

import struct
import time
from typing import List, Dict, Optional, Tuple

import serial
import serial.tools.list_ports

from .color_match import ArtkalPalette


MAGIC_HEADER = bytes([0xBC, 0xD1, 0x32, 0x57])
BAUD_RATE = 460800  # Optimized baud rate
TIMEOUT = 10.0  # seconds
IMAGE_SIZE = 8192  # 64x64 * 2 bytes


# === Persistent Serial Connection Pool ===
_serial_connections = {}  # port -> Serial object
_connection_states = {}   # port -> {'ready': bool, 'last_used': float}


def get_serial_connection(port: str, baud_rate: int = BAUD_RATE) -> serial.Serial:
    """Get or create persistent serial connection."""
    global _serial_connections, _connection_states
    
    # Check if connection exists and is open
    if port in _serial_connections:
        ser = _serial_connections[port]
        if ser.is_open:
            return ser
        else:
            # Connection closed, remove it
            del _serial_connections[port]
            if port in _connection_states:
                del _connection_states[port]
    
    # Create new connection (will trigger ESP32 reset)
    print(f"[DEBUG] Creating new serial connection to {port}")
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud_rate
    ser.timeout = TIMEOUT
    ser.write_timeout = TIMEOUT
    ser.dtr = False
    ser.rts = False
    ser.open()
    
    # Set DTR/RTS after open
    ser.dtr = False
    ser.rts = False
    
    _serial_connections[port] = ser
    _connection_states[port] = {'ready': False, 'last_used': time.time()}
    
    return ser


def wait_for_esp32_ready(ser: serial.Serial, port: str, timeout: float = 5.0) -> bool:
    """Wait for ESP32 to be ready after connection."""
    global _connection_states
    
    # If already ready, return immediately
    if port in _connection_states and _connection_states[port]['ready']:
        return True
    
    print(f"[DEBUG] Waiting for ESP32 ready on {port}...")
    
    # Clear buffers
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    # Wait for READY message (ESP32 sends it after boot)
    start = time.time()
    while time.time() - start < timeout:
        if ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(f"[ESP32] {line}")
                if 'READY' in line:
                    print(f"[DEBUG] ESP32 ready!")
                    if port in _connection_states:
                        _connection_states[port]['ready'] = True
                    return True
            except:
                pass
        time.sleep(0.05)
    
    # Timeout - assume ready anyway (ESP32 might already be running)
    print(f"[DEBUG] READY timeout, assuming ready...")
    if port in _connection_states:
        _connection_states[port]['ready'] = True
    return True


def rgb_to_rgb565(r: int, g: int, b: int) -> int:
    """Convert 8-bit RGB to RGB565 format.
    
    RGB565: RRRRRGGGGGGBBBBB (5-6-5 bits)
    """
    r5 = (r >> 3) & 0x1F  # 5 bits
    g6 = (g >> 2) & 0x3F  # 6 bits
    b5 = (b >> 3) & 0x1F  # 5 bits
    return (r5 << 11) | (g6 << 5) | b5


def pixel_matrix_to_rgb565(
    pixel_matrix: List[List[Optional[str]]],
    palette: ArtkalPalette,
    background_color: Tuple[int, int, int] = (0, 0, 0),
) -> bytes:
    """Convert pixel matrix to RGB565 binary data.
    
    Args:
        pixel_matrix: 2D list of color codes (or None for transparent)
        palette: ArtkalPalette instance for color lookups
        background_color: RGB tuple for transparent/None cells
    
    Returns:
        Bytes of RGB565 data (little-endian uint16 per pixel)
    """
    if not pixel_matrix or not pixel_matrix[0]:
        return b''
    
    height = len(pixel_matrix)
    width = len(pixel_matrix[0])
    
    data = bytearray()
    
    for row in pixel_matrix:
        for code in row:
            if code is None:
                r, g, b = background_color
            else:
                color_info = palette.get_by_code(code)
                if color_info:
                    r, g, b = color_info['rgb']
                else:
                    r, g, b = 255, 255, 255  # White for unknown
            
            rgb565 = rgb_to_rgb565(r, g, b)
            data.extend(struct.pack('<H', rgb565))  # little-endian uint16
    
    return bytes(data)


def center_in_bounds(
    pixel_matrix: List[List[Optional[str]]],
    target_width: int,
    target_height: int,
) -> List[List[Optional[str]]]:
    """Center image in larger bounds (no scaling, just pad with None).
    
    Args:
        pixel_matrix: Pixel matrix (must be <= target size)
        target_width: Target width
        target_height: Target height
    
    Returns:
        Centered pixel matrix of target_width x target_height
    """
    if not pixel_matrix or not pixel_matrix[0]:
        return [[None] * target_width for _ in range(target_height)]
    
    src_height = len(pixel_matrix)
    src_width = len(pixel_matrix[0])
    
    # Create output matrix filled with None
    result = [[None] * target_width for _ in range(target_height)]
    
    # Calculate offset to center
    offset_x = (target_width - src_width) // 2
    offset_y = (target_height - src_height) // 2
    
    # Copy source to centered position
    for y in range(src_height):
        for x in range(src_width):
            result[y + offset_y][x + offset_x] = pixel_matrix[y][x]
    
    return result


def scale_and_center_image(
    pixel_matrix: List[List[Optional[str]]],
    led_width: int,
    led_height: int,
) -> List[List[Optional[str]]]:
    """Scale and center image to LED matrix size.
    
    Args:
        pixel_matrix: Original pixel matrix
        led_width: LED matrix width
        led_height: LED matrix height
    
    Returns:
        Scaled and centered pixel matrix of led_width x led_height
    """
    if not pixel_matrix or not pixel_matrix[0]:
        return [[None] * led_width for _ in range(led_height)]
    
    src_height = len(pixel_matrix)
    src_width = len(pixel_matrix[0])
    
    # Create output matrix filled with None
    result = [[None] * led_width for _ in range(led_height)]
    
    # Calculate scale factor (fit within LED bounds)
    scale = min(led_width / src_width, led_height / src_height)
    
    # Calculate scaled dimensions
    scaled_width = int(src_width * scale)
    scaled_height = int(src_height * scale)
    
    # Calculate offset to center
    offset_x = (led_width - scaled_width) // 2
    offset_y = (led_height - scaled_height) // 2
    
    # Map each LED pixel to source image pixel
    for led_y in range(led_height):
        for led_x in range(led_width):
            # Check if this LED pixel is within the scaled image bounds
            rel_x = led_x - offset_x
            rel_y = led_y - offset_y
            
            if 0 <= rel_x < scaled_width and 0 <= rel_y < scaled_height:
                # Map to source coordinates
                src_x = int(rel_x / scale)
                src_y = int(rel_y / scale)
                
                # Clamp to source bounds
                src_x = max(0, min(src_x, src_width - 1))
                src_y = max(0, min(src_y, src_height - 1))
                
                result[led_y][led_x] = pixel_matrix[src_y][src_x]
    
    return result


def build_packet(
    pixel_matrix: List[List[Optional[str]]],
    palette: ArtkalPalette,
    background_color: Tuple[int, int, int] = (0, 0, 0),
    led_matrix_size: Tuple[int, int] = (64, 64),
) -> bytes:
    """Build optimized binary packet for transmission.
    
    Args:
        pixel_matrix: 2D list of color codes
        palette: ArtkalPalette instance
        background_color: RGB for transparent cells
        led_matrix_size: (width, height) of LED matrix (for scaling)
    
    Packet structure:
    - 4 bytes: Magic header
    - 8192 bytes: RGB565 data (always 64x64 for ESP32)
    - 2 bytes: Checksum (uint16 LE)
    """
    if not pixel_matrix or not pixel_matrix[0]:
        raise ValueError("Empty pixel matrix")
    
    led_width, led_height = led_matrix_size
    
    # Step 1: Scale image to fit within LED bounds
    scaled_matrix = scale_and_center_image(pixel_matrix, led_width, led_height)
    
    # Step 2: Center scaled image in 64x64 canvas (for ESP32)
    # If LED is 52x52, the scaled image will be 52x52, centered in 64x64
    final_matrix = center_in_bounds(scaled_matrix, 64, 64)
    
    # Build data (always 8192 bytes for 64x64)
    rgb565_data = pixel_matrix_to_rgb565(final_matrix, palette, background_color)
    
    # Ensure correct size (8192 bytes)
    if len(rgb565_data) < IMAGE_SIZE:
        rgb565_data += b'\x00' * (IMAGE_SIZE - len(rgb565_data))
    elif len(rgb565_data) > IMAGE_SIZE:
        rgb565_data = rgb565_data[:IMAGE_SIZE]
    
    # Calculate checksum (sum of all data bytes)
    checksum = sum(rgb565_data) & 0xFFFF
    
    # Build packet
    packet = bytearray()
    packet.extend(MAGIC_HEADER)
    packet.extend(rgb565_data)
    packet.extend(struct.pack('<H', checksum))
    
    return bytes(packet)


def list_available_ports() -> List[Dict[str, str]]:
    """List all available serial ports.
    
    Returns:
        List of dicts with 'device', 'description', 'hwid' keys
    """
    ports = []
    for port in serial.tools.list_ports.comports():
        ports.append({
            'device': port.device,
            'description': port.description,
            'hwid': port.hwid or '',
        })
    return ports


def read_serial_log(
    port: str,
    baud_rate: int = BAUD_RATE,
    duration_ms: int = 3000,
) -> List[str]:
    """Read serial log for a specified duration.
    
    Args:
        port: Serial port device
        baud_rate: Baud rate
        duration_ms: Duration to read in milliseconds
    
    Returns:
        List of log lines
    """
    logs = []
    start_time = time.time()
    
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud_rate,
            timeout=0.1,
        )
        
        while (time.time() - start_time) * 1000 < duration_ms:
            if ser.in_waiting > 0:
                line = ser.readline()
                if line:
                    try:
                        logs.append(line.decode('utf-8', errors='ignore').strip())
                    except:
                        pass
            time.sleep(0.01)
        
        ser.close()
    except Exception as e:
        logs.append(f"[Error reading log: {str(e)}]")
    
    return logs


def stream_serial_log(
    port: str,
    baud_rate: int = BAUD_RATE,
    duration_ms: int = 10000,
):
    """Generator that yields serial log lines in real-time.
    
    Yields:
        str: Each line from serial port
    """
    start_time = time.time()
    ser = None
    
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud_rate,
            timeout=0.05,
        )
        
        while (time.time() - start_time) * 1000 < duration_ms:
            if ser.in_waiting > 0:
                line = ser.readline()
                if line:
                    try:
                        line_str = line.decode('utf-8', errors='ignore').strip()
                        if line_str:
                            yield line_str
                    except:
                        pass
            else:
                time.sleep(0.01)
        
        ser.close()
        ser = None
        
    except Exception as e:
        yield f"[Error: {str(e)}]"
    finally:
        if ser:
            try:
                ser.close()
            except:
                pass


def send_to_esp32(
    pixel_matrix: List[List[Optional[str]]],
    palette: ArtkalPalette,
    port: str,
    baud_rate: int = BAUD_RATE,
    background_color: Tuple[int, int, int] = (0, 0, 0),
    led_matrix_size: Tuple[int, int] = (64, 64),
    wait_for_ack: bool = True,
    read_log: bool = True,
    log_duration_ms: int = 3000,
) -> Dict[str, any]:
    """Send pixel matrix to ESP32 via serial port.
    
    Args:
        pixel_matrix: 2D list of color codes
        palette: ArtkalPalette instance
        port: Serial port device (e.g., 'COM3' or '/dev/ttyUSB0')
        baud_rate: Baud rate (default 460800)
        background_color: RGB for transparent cells
        led_matrix_size: (width, height) of LED matrix
        wait_for_ack: Whether to wait for ACK response
        read_log: Whether to read serial log after sending
        log_duration_ms: Duration to read log in milliseconds
    
    Returns:
        Dict with 'success', 'message', 'bytes_sent', 'duration_ms', 'grid_size', 'logs'
    """
    start_time = time.time()
    
    try:
        # Build packet (scales and centers image to LED size)
        packet = build_packet(pixel_matrix, palette, background_color, led_matrix_size)
        
        width = len(pixel_matrix[0]) if pixel_matrix else 0
        height = len(pixel_matrix)
        led_w, led_h = led_matrix_size
        print(f"[DEBUG] Sending packet: {width}x{height} -> {led_w}x{led_h}, {len(packet)} bytes")
        
        # Get persistent serial connection (only first time triggers ESP32 reset)
        ser = get_serial_connection(port, baud_rate)
        
        # Wait for ESP32 ready (only first time)
        if not wait_for_esp32_ready(ser, port):
            print(f"[DEBUG] ESP32 not ready, proceeding anyway...")
        
        # Clear buffers before sending
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        # Send in chunks for reliability
        chunk_size = 512
        bytes_written = 0
        for i in range(0, len(packet), chunk_size):
            chunk = packet[i:i+chunk_size]
            bytes_written += ser.write(chunk)
            ser.flush()
            time.sleep(0.01)  # 10ms delay between chunks
        
        print(f"[DEBUG] Sent {bytes_written} bytes in {(time.time()-start_time)*1000:.0f}ms")
        
        # Wait for ACK if requested
        ack_received = False
        ack_message = ''
        all_logs = []
        
        if wait_for_ack:
            # Wait for response: HDR, DATA_OK, CS_OK, OK
            deadline = time.time() + TIMEOUT
            while time.time() < deadline:
                if ser.in_waiting > 0:
                    response = ser.readline()
                    if response:
                        response_str = response.decode('utf-8', errors='ignore').strip()
                        all_logs.append(response_str)
                        
                        if response_str == 'OK' or response_str == 'OK_HL':
                            ack_received = True
                            ack_message = response_str
                            break
                        elif response_str.startswith('CS_ERR'):
                            ack_message = response_str
                            break
        
        # Don't close connection - keep it persistent for faster subsequent sends
        # Connection will be reused by get_serial_connection()
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        return {
            'success': ack_received if wait_for_ack else True,
            'message': ack_message if wait_for_ack else 'Data sent successfully',
            'bytes_sent': bytes_written,
            'duration_ms': duration_ms,
            'grid_size': [len(pixel_matrix[0]), len(pixel_matrix)],
            'logs': all_logs,
        }
        
    except serial.SerialException as e:
        return {
            'success': False,
            'message': f'Serial error: {str(e)}',
            'bytes_sent': 0,
            'duration_ms': int((time.time() - start_time) * 1000),
            'logs': [],
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Error: {str(e)}',
            'bytes_sent': 0,
            'duration_ms': int((time.time() - start_time) * 1000),
            'logs': [],
        }


def send_highlight_serial(
    highlight_colors: List[Tuple[int, int, int]],
    port: str,
    baud_rate: int = BAUD_RATE,
) -> dict:
    """Send highlight command to ESP32 via serial.

    Protocol:
        - Highlight: 0x04 + count(1B) + RGB565 colors(N*2B)
        - Show All: 0x05

    Args:
        highlight_colors: List of RGB tuples to highlight (empty = show all)
        port: Serial port name
        baud_rate: Baud rate

    Returns:
        Dict with 'success', 'message', 'logs'
    """
    start_time = time.time()
    logs = []

    try:
        # Use persistent connection (same as send_to_esp32)
        ser = get_serial_connection(port, baud_rate)
        
        # Wait for ready if first time
        if not wait_for_esp32_ready(ser, port):
            print(f"[DEBUG] ESP32 not ready for highlight...")

        ser.reset_input_buffer()

        if not highlight_colors:
            # Show all: send 0x05
            packet = bytes([0x05])
            logs.append("Sending SHOW_ALL command")
        else:
            # Highlight: 0x04 + count + RGB565 colors
            packet = bytearray([0x04, len(highlight_colors)])
            for r, g, b in highlight_colors:
                rgb565 = rgb_to_rgb565(r, g, b)
                packet.extend(struct.pack('<H', rgb565))
            logs.append(f"Sending HIGHLIGHT command: {len(highlight_colors)} colors")

        ser.write(packet)
        ser.flush()

        # Read response
        response_lines = []
        timeout_time = time.time() + 1.0
        while time.time() < timeout_time:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    response_lines.append(line)
                    logs.append(f"[ESP32] {line}")
                    if "HIGHLIGHT" in line or "SHOW_ALL" in line or "OK" in line:
                        break
            time.sleep(0.01)

        # Don't close - keep connection persistent

        return {
            'success': True,
            'message': f'Highlight {len(highlight_colors)} colors',
            'duration_ms': int((time.time() - start_time) * 1000),
            'logs': response_lines,
        }

    except Exception as e:
        return {
            'success': False,
            'message': str(e),
            'duration_ms': int((time.time() - start_time) * 1000),
            'logs': logs,
        }
