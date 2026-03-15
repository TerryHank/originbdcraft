"""BLE export module for sending pixel matrix to ESP32 via Bluetooth Low Energy.

Protocol:
- Packet type 0x01: Start image
- Packet type 0x02: Data chunk (up to 20 bytes per BLE packet)
- Packet type 0x03: End image
"""

import asyncio
import struct
from typing import List, Optional, Tuple

from bleak import BleakClient, BleakScanner

from .color_match import ArtkalPalette


SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea0734b3e6c1"
IMAGE_SIZE = 8192  # 64x64 * 2 bytes
MTU_SIZE = 20  # BLE default MTU - 3 (header)


def rgb_to_rgb565(r: int, g: int, b: int) -> int:
    """Convert 8-bit RGB to RGB565 format."""
    r5 = (r >> 3) & 0x1F
    g6 = (g >> 2) & 0x3F
    b5 = (b >> 3) & 0x1F
    return (r5 << 11) | (g6 << 5) | b5


def pixel_matrix_to_rgb565(
    pixel_matrix: List[List[Optional[str]]],
    palette: ArtkalPalette,
    background_color: Tuple[int, int, int] = (0, 0, 0),
) -> bytes:
    """Convert pixel matrix to RGB565 binary data."""
    if not pixel_matrix or not pixel_matrix[0]:
        return b''
    
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
                    r, g, b = 255, 255, 255
            
            rgb565 = rgb_to_rgb565(r, g, b)
            data.extend(struct.pack('<H', rgb565))
    
    # Pad to IMAGE_SIZE
    if len(data) < IMAGE_SIZE:
        data += b'\x00' * (IMAGE_SIZE - len(data))
    elif len(data) > IMAGE_SIZE:
        data = data[:IMAGE_SIZE]
    
    return bytes(data)


async def scan_ble_devices() -> List[dict]:
    """Scan for available BLE devices."""
    devices = await BleakScanner.discover()
    result = []
    for d in devices:
        if d.name and "BeadCraft" in d.name:
            result.append({
                'address': d.address,
                'name': d.name,
            })
    return result


async def send_to_esp32_ble(
    pixel_matrix: List[List[Optional[str]]],
    palette: ArtkalPalette,
    device_address: str = None,
    background_color: Tuple[int, int, int] = (0, 0, 0),
    timeout: float = 30.0,
) -> dict:
    """Send pixel matrix to ESP32 via BLE.
    
    Args:
        pixel_matrix: 2D list of color codes
        palette: ArtkalPalette instance
        device_address: BLE device address (auto-detect if None)
        background_color: RGB for transparent cells
        timeout: Connection timeout in seconds
    
    Returns:
        Dict with 'success', 'message', 'bytes_sent', 'duration_ms'
    """
    import time
    start_time = time.time()
    
    try:
        # Convert to RGB565
        rgb565_data = pixel_matrix_to_rgb565(pixel_matrix, palette, background_color)
        
        # Auto-detect device if not specified
        if not device_address:
            devices = await scan_ble_devices()
            if not devices:
                return {
                    'success': False,
                    'message': 'No BeadCraft BLE device found',
                    'bytes_sent': 0,
                    'duration_ms': int((time.time() - start_time) * 1000),
                }
            device_address = devices[0]['address']
        
        # Connect and send
        async with BleakClient(device_address, timeout=timeout) as client:
            print(f"[BLE] Connected to {device_address}")
            
            # Send start packet
            await client.write_gatt_char(CHARACTERISTIC_UUID, bytes([0x01]))
            
            # Send data in chunks (19 bytes per chunk, 1 byte for packet type)
            chunk_size = 19
            bytes_sent = 0
            
            for i in range(0, len(rgb565_data), chunk_size):
                chunk = rgb565_data[i:i+chunk_size]
                packet = bytes([0x02]) + chunk
                await client.write_gatt_char(CHARACTERISTIC_UUID, packet)
                bytes_sent += len(chunk)
                await asyncio.sleep(0.01)  # Small delay to avoid overwhelming
            
            # Send end packet
            await client.write_gatt_char(CHARACTERISTIC_UUID, bytes([0x03]))
            
            print(f"[BLE] Sent {bytes_sent} bytes")
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        return {
            'success': True,
            'message': 'Image sent successfully',
            'bytes_sent': bytes_sent,
            'duration_ms': duration_ms,
            'device': device_address,
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'BLE error: {str(e)}',
            'bytes_sent': 0,
            'duration_ms': int((time.time() - start_time) * 1000),
        }


def send_to_esp32_ble_sync(
    pixel_matrix: List[List[Optional[str]]],
    palette: ArtkalPalette,
    device_address: str = None,
    background_color: Tuple[int, int, int] = (0, 0, 0),
    timeout: float = 30.0,
) -> dict:
    """Synchronous wrapper for BLE send."""
    return asyncio.run(send_to_esp32_ble(
        pixel_matrix, palette, device_address, background_color, timeout
    ))


async def send_highlight_ble(
    highlight_colors: List[Tuple[int, int, int]],
    device_address: str = None,
    timeout: float = 10.0,
) -> dict:
    """Send highlight command to ESP32 via BLE.
    
    Args:
        highlight_colors: List of RGB tuples to highlight
        device_address: BLE device address (auto-detect if None)
        timeout: Connection timeout
    
    Returns:
        Dict with 'success', 'message'
    """
    import time
    start_time = time.time()
    
    try:
        # Auto-detect device if not specified
        if not device_address:
            devices = await scan_ble_devices()
            if not devices:
                return {
                    'success': False,
                    'message': 'No BeadCraft BLE device found',
                }
            device_address = devices[0]['address']
        
        # Convert RGB to RGB565
        rgb565_colors = []
        for r, g, b in highlight_colors:
            rgb565 = rgb_to_rgb565(r, g, b)
            rgb565_colors.append(rgb565)
        
        # Build packet: [0x04][count][RGB565...]
        packet = bytearray([0x04, len(rgb565_colors)])
        for color in rgb565_colors:
            packet.extend(struct.pack('<H', color))
        
        # Connect and send
        async with BleakClient(device_address, timeout=timeout) as client:
            await client.write_gatt_char(CHARACTERISTIC_UUID, bytes(packet))
        
        return {
            'success': True,
            'message': f'Highlight {len(highlight_colors)} colors',
            'duration_ms': int((time.time() - start_time) * 1000),
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'BLE error: {str(e)}',
        }


def send_highlight_ble_sync(
    highlight_colors: List[Tuple[int, int, int]],
    device_address: str = None,
    timeout: float = 10.0,
) -> dict:
    """Synchronous wrapper for BLE highlight."""
    return asyncio.run(send_highlight_ble(highlight_colors, device_address, timeout))
