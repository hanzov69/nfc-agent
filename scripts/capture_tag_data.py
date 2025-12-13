#!/usr/bin/env python3
"""
NFC Tag Data Capture Script

This script connects to the NFC Agent WebSocket API and captures raw APDU
responses for each tag type. The captured data is used for regression testing.

Usage:
    1. Start nfc-agent with: NFC_CAPTURE_LOG=1 ./nfc-agent
    2. Run this script: python3 scripts/capture_tag_data.py
    3. Follow the prompts to scan each tag type
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import websockets
except ImportError:
    print("Error: websockets library required. Install with: pip3 install websockets")
    sys.exit(1)

# Configuration
WS_URL = "ws://127.0.0.1:32145/v1/ws"
CAPTURE_LOG = Path("nfc_capture.log")
TESTDATA_DIR = Path("internal/core/testdata")

# Tag types to capture (in order)
TAG_TYPES = [
    ("NTAG213", "ntag213"),
    ("NTAG215", "ntag215"),
    ("NTAG216", "ntag216"),
    ("ICode Slix2", "icode_slix2"),
    ("MIFARE Classic 1K", "mifare_classic"),
    ("MIFARE Ultralight", "mifare_ultralight"),
]

# Reader ID mapping (normalized names)
READER_IDS = {
    "ACR1552": "acr1552u",
    "ACR122U": "acr122u",
    "ACR1252": "acr1252u",
}


def get_reader_id(reader_name: str) -> str:
    """Extract reader ID from full reader name."""
    reader_upper = reader_name.upper()
    for key, value in READER_IDS.items():
        if key in reader_upper:
            return value
    # Fallback: sanitize the name
    return reader_name.lower().replace(" ", "_").replace("/", "_")[:20]


def parse_capture_log() -> dict:
    """Parse the capture log file and return responses by method."""
    responses = {}
    if not CAPTURE_LOG.exists():
        return responses

    with open(CAPTURE_LOG, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Format: timestamp | method | cmd=xxx | rsp=xxx
            parts = line.split(" | ")
            if len(parts) >= 4:
                method = parts[1]
                cmd_part = parts[2]
                rsp_part = parts[3]

                cmd = cmd_part.replace("cmd=", "")
                rsp = rsp_part.replace("rsp=", "")

                responses[method.lower()] = {
                    "cmd": cmd,
                    "rsp": rsp,
                }

    return responses


def clear_capture_log():
    """Clear the capture log file."""
    if CAPTURE_LOG.exists():
        CAPTURE_LOG.unlink()


async def list_readers(ws) -> list:
    """Get list of connected readers."""
    msg = {
        "type": "list_readers",
        "id": "list-1"
    }
    await ws.send(json.dumps(msg))

    response = await ws.recv()
    data = json.loads(response)

    if data.get("error"):
        print(f"Error listing readers: {data['error']}")
        return []

    readers = json.loads(data.get("payload", "[]"))
    return readers


async def subscribe_to_reader(ws, reader_index: int):
    """Subscribe to card detection events for a reader."""
    msg = {
        "type": "subscribe",
        "id": "sub-1",
        "payload": {
            "readerIndex": reader_index,
            "intervalMs": 500
        }
    }
    await ws.send(json.dumps(msg))

    response = await ws.recv()
    data = json.loads(response)

    if data.get("error"):
        print(f"Error subscribing: {data['error']}")
        return False

    return True


async def unsubscribe_from_reader(ws, reader_index: int):
    """Unsubscribe from card detection events."""
    msg = {
        "type": "unsubscribe",
        "id": "unsub-1",
        "payload": {
            "readerIndex": reader_index
        }
    }
    await ws.send(json.dumps(msg))
    await ws.recv()


async def wait_for_card(ws, timeout: float = 60.0) -> dict | None:
    """Wait for a card to be detected."""
    try:
        while True:
            response = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(response)

            if data.get("type") == "card_detected":
                payload = json.loads(data.get("payload", "{}"))
                return payload.get("card")
    except asyncio.TimeoutError:
        return None


async def wait_for_card_removal(ws, timeout: float = 30.0):
    """Wait for a card to be removed."""
    try:
        while True:
            response = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(response)

            if data.get("type") == "card_removed":
                return True
    except asyncio.TimeoutError:
        return False


def save_capture_data(reader_id: str, tag_file: str, card_data: dict, responses: dict, reader_name: str, tag_display: str):
    """Save captured data to JSON file."""
    output_dir = TESTDATA_DIR / reader_id
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{tag_file}.json"

    # Build the capture data structure
    capture_data = {
        "reader": reader_name,
        "reader_id": reader_id,
        "tag_type": tag_display,
        "uid": card_data.get("uid", ""),
        "atr": card_data.get("atr", ""),
        "protocol": card_data.get("protocol", ""),
        "protocol_iso": card_data.get("protocolISO", ""),
        "responses": {},
        "detected_type": card_data.get("type", ""),
        "detected_size": card_data.get("size", 0),
        "captured_at": datetime.now().isoformat(),
    }

    # Add raw responses
    for method, data in responses.items():
        capture_data["responses"][method] = data["rsp"]

    with open(output_file, 'w') as f:
        json.dump(capture_data, f, indent=2)

    print(f"    Saved to: {output_file}")


async def capture_tags_for_reader(reader_name: str, reader_index: int, skip_iso15693: bool = False):
    """Capture tag data for a specific reader."""
    reader_id = get_reader_id(reader_name)
    print(f"\n{'='*60}")
    print(f"Capturing tags for: {reader_name}")
    print(f"Reader ID: {reader_id}")
    print(f"{'='*60}")

    async with websockets.connect(WS_URL) as ws:
        # Subscribe to card events
        if not await subscribe_to_reader(ws, reader_index):
            print("Failed to subscribe to reader")
            return

        tags_to_capture = TAG_TYPES.copy()
        if skip_iso15693:
            tags_to_capture = [(t, f) for t, f in tags_to_capture if "slix" not in f.lower()]

        for tag_display, tag_file in tags_to_capture:
            print(f"\n--- {tag_display} ---")

            # Clear capture log before scanning
            clear_capture_log()

            input(f"Place {tag_display} on the reader and press Enter...")

            # Wait for card detection
            print("  Waiting for card...")
            card_data = await wait_for_card(ws, timeout=30.0)

            if not card_data:
                print(f"  ERROR: No card detected within timeout")
                retry = input("  Retry? (y/n): ")
                if retry.lower() == 'y':
                    card_data = await wait_for_card(ws, timeout=30.0)
                if not card_data:
                    continue

            # Give a moment for all APDU commands to complete and be logged
            await asyncio.sleep(0.5)

            # Read capture log
            responses = parse_capture_log()

            print(f"  UID: {card_data.get('uid', 'N/A')}")
            print(f"  ATR: {card_data.get('atr', 'N/A')}")
            print(f"  Detected Type: {card_data.get('type', 'N/A')}")
            print(f"  Protocol: {card_data.get('protocol', 'N/A')} ({card_data.get('protocolISO', 'N/A')})")
            print(f"  Captured {len(responses)} APDU responses")

            # Check if detected type matches expected
            detected = card_data.get('type', '').upper()
            expected = tag_display.upper().replace(" 1K", "")
            if expected not in detected and detected not in expected:
                print(f"  WARNING: Detected type '{card_data.get('type')}' doesn't match expected '{tag_display}'")
                confirm = input("  Save anyway? (y/n): ")
                if confirm.lower() != 'y':
                    continue

            # Save capture data
            save_capture_data(reader_id, tag_file, card_data, responses, reader_name, tag_display)

            # Wait for card removal
            print("  Remove the card...")
            await wait_for_card_removal(ws, timeout=10.0)
            await asyncio.sleep(0.5)

        # Unsubscribe
        await unsubscribe_from_reader(ws, reader_index)

    print(f"\nCompleted capture for {reader_name}")


async def main():
    print("NFC Tag Data Capture Script")
    print("="*60)
    print()
    print("Prerequisites:")
    print("  1. nfc-agent must be running with NFC_CAPTURE_LOG=1")
    print("  2. A reader must be connected")
    print()

    # Connect and list readers
    try:
        async with websockets.connect(WS_URL) as ws:
            readers = await list_readers(ws)
    except Exception as e:
        print(f"Error connecting to NFC Agent: {e}")
        print("Make sure nfc-agent is running with: NFC_CAPTURE_LOG=1 ./nfc-agent")
        sys.exit(1)

    if not readers:
        print("No readers found!")
        sys.exit(1)

    print("Available readers:")
    for i, reader in enumerate(readers):
        print(f"  [{i}] {reader.get('name', 'Unknown')}")
    print()

    # Select reader
    while True:
        try:
            selection = input("Select reader index (or 'all' for all readers): ")
            if selection.lower() == 'all':
                selected_indices = list(range(len(readers)))
                break
            else:
                idx = int(selection)
                if 0 <= idx < len(readers):
                    selected_indices = [idx]
                    break
                print("Invalid index")
        except ValueError:
            print("Invalid input")

    # Capture for selected readers
    for idx in selected_indices:
        reader = readers[idx]
        reader_name = reader.get('name', f'Reader {idx}')

        # Check if reader supports ISO 15693
        skip_iso15693 = "ACR122U" in reader_name.upper() or "ACR1252" in reader_name.upper()
        if skip_iso15693:
            print(f"\nNote: {reader_name} does not support ISO 15693 (ICode Slix2)")

        await capture_tags_for_reader(reader_name, idx, skip_iso15693)

    print("\n" + "="*60)
    print("Capture complete!")
    print(f"Data saved to: {TESTDATA_DIR}/")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
