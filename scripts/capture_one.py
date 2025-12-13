#!/usr/bin/env python3
"""Capture a single tag (MIFARE Ultralight)."""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
import websockets

TAG_NAME = "MIFARE Ultralight"
TAG_FILE = "mifare_ultralight"

WS_URL = "ws://127.0.0.1:32145/v1/ws"
CAPTURE_LOG = Path("nfc_capture.log")
TESTDATA_DIR = Path("internal/core/testdata")

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

async def main():
    print(f"Capture: {TAG_NAME}")
    print(f"Connecting to {WS_URL}...")

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

        print(f">>> Place {TAG_NAME} on reader...")

        while True:
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=30.0)
                data = json.loads(resp)

                if data.get("type") == "card_detected":
                    payload = data.get("payload", {})
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    card = payload.get("card", {})
                    uid = card.get("uid", "")

                    if uid:
                        await asyncio.sleep(0.3)
                        responses = parse_capture_log()

                        print(f"\nCaptured!")
                        print(f"  UID: {uid}")
                        print(f"  ATR: {card.get('atr', '?')}")
                        print(f"  Detected as: {card.get('type', '?')}")
                        print(f"  Protocol: {card.get('protocol', '?')} / {card.get('protocolISO', '?')}")

                        # Save
                        output_dir = TESTDATA_DIR / reader_id
                        output_dir.mkdir(parents=True, exist_ok=True)
                        output_file = output_dir / f"{TAG_FILE}.json"

                        out_data = {
                            "reader": reader_name,
                            "reader_id": reader_id,
                            "tag_type": TAG_NAME,
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
                            json.dump(out_data, f, indent=2)
                        print(f"  -> Saved: {output_file}")
                        return

            except asyncio.TimeoutError:
                print("Timeout waiting for tag...")
                return

if __name__ == "__main__":
    asyncio.run(main())
