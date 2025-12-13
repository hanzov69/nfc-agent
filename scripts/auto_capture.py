#!/usr/bin/env python3
"""
Captures 6 tags in order: NTAG213, NTAG215, NTAG216, ICode Slix2, MIFARE Classic, MIFARE Ultralight
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
    print("pip3 install websockets")
    sys.exit(1)

WS_URL = "ws://127.0.0.1:32145/v1/ws"
CAPTURE_LOG = Path("nfc_capture.log")
TESTDATA_DIR = Path("internal/core/testdata")

# Tags in order (ICode Slix2 commented out - not supported by ACR122U/ACR1252U)
TAGS = [
    ("NTAG213", "ntag213"),
    ("NTAG215", "ntag215"),
    ("NTAG216", "ntag216"),
    # ("ICode Slix2", "icode_slix2"),
    ("MIFARE Classic", "mifare_classic"),
    ("MIFARE Ultralight", "mifare_ultralight"),
]

def get_reader_id(name):
    if "1552" in name: return "acr1552u"
    if "122U" in name.upper(): return "acr122u"
    if "1252" in name: return "acr1252u"
    return "unknown"

def parse_capture_log():
    responses = {}
    if not CAPTURE_LOG.exists():
        return responses
    with open(CAPTURE_LOG, 'r') as f:
        for line in f:
            parts = line.strip().split(" | ")
            if len(parts) >= 4:
                method = parts[1]
                rsp = parts[3].replace("rsp=", "")
                responses[method.lower()] = rsp
    return responses

def clear_capture_log():
    if CAPTURE_LOG.exists():
        CAPTURE_LOG.unlink()

def save(reader_id, tag_file, tag_name, card, responses, reader_name):
    output_dir = TESTDATA_DIR / reader_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{tag_file}.json"

    data = {
        "reader": reader_name,
        "reader_id": reader_id,
        "tag_type": tag_name,
        "uid": card.get("uid", ""),
        "atr": card.get("atr", ""),
        "protocol": card.get("protocol", ""),
        "protocol_iso": card.get("protocolISO", ""),
        "responses": responses,
        "detected_type": card.get("type", ""),
        "detected_size": card.get("size", 0),
        "captured_at": datetime.now().isoformat(),
    }

    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"  -> Saved: {output_file}")

async def main():
    print(f"Capture {len(TAGS)} tag(s):")
    for i, (name, _) in enumerate(TAGS):
        print(f"  {i+1}. {name}")
    print()

    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "list_readers", "id": "1"}))
            resp = json.loads(await ws.recv())
            payload = resp.get("payload", [])
            readers = json.loads(payload) if isinstance(payload, str) else payload

            if not readers:
                print("No readers!")
                return

            reader_name = readers[0].get("name", "Unknown")
            reader_id = get_reader_id(reader_name)
            print(f"Reader: {reader_name} ({reader_id})\n")

            await ws.send(json.dumps({"type": "subscribe", "id": "2", "payload": {"readerIndex": 0, "intervalMs": 500}}))
            await ws.recv()

            last_uid = None
            tag_index = 0

            print(f"Waiting for tag 1/{len(TAGS)}: {TAGS[0][0]}...")

            while tag_index < len(TAGS):
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    data = json.loads(resp)

                    if data.get("type") == "card_detected":
                        payload = data.get("payload", {})
                        if isinstance(payload, str):
                            payload = json.loads(payload)
                        card = payload.get("card", {})
                        uid = card.get("uid", "")

                        if uid and uid != last_uid:
                            last_uid = uid
                            tag_name, tag_file = TAGS[tag_index]

                            await asyncio.sleep(0.3)
                            responses = parse_capture_log()

                            print(f"\n[{tag_index+1}/{len(TAGS)}] {tag_name}")
                            print(f"  UID: {uid}")
                            print(f"  Detected as: {card.get('type', '?')} (size={card.get('size', '?')})")
                            print(f"  Protocol: {card.get('protocol', '?')} / {card.get('protocolISO', '?')}")
                            print(f"  APDU responses: {len(responses)}")

                            save(reader_id, tag_file, tag_name, card, responses, reader_name)
                            clear_capture_log()

                            tag_index += 1
                            if tag_index < len(TAGS):
                                print(f"\nRemove tag, then scan {tag_index+1}/{len(TAGS)}: {TAGS[tag_index][0]}...")

                    elif data.get("type") == "card_removed":
                        last_uid = None

                except asyncio.TimeoutError:
                    continue

            print("\n" + "="*50)
            print(f"ALL {len(TAGS)} TAG(S) CAPTURED!")
            print("="*50)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
