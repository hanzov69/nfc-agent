#!/usr/bin/env python3
"""Test script for MIFARE Ultralight and MIFARE Classic write operations."""

import requests
import sys

BASE_URL = "http://127.0.0.1:32145/v1"

def get_readers():
    """Get list of available readers."""
    resp = requests.get(f"{BASE_URL}/readers")
    resp.raise_for_status()
    return resp.json()

def get_card(reader_index=0):
    """Get card info from reader."""
    resp = requests.get(f"{BASE_URL}/readers/{reader_index}/card")
    if resp.status_code == 200:
        return resp.json()
    return None

def test_ultralight_write(reader_index=0):
    """Test MIFARE Ultralight / NTAG page writes."""
    print("\n=== Testing MIFARE Ultralight / NTAG Write ===")

    # Get card info first
    card = get_card(reader_index)
    if not card:
        print("❌ No card detected")
        return False

    print(f"Card detected: {card.get('type', 'Unknown')} (UID: {card.get('uid', 'N/A')})")

    if "NTAG" not in card.get('type', '') and "Ultralight" not in card.get('type', ''):
        print(f"⚠️  Card type '{card.get('type')}' may not be MIFARE Ultralight/NTAG")

    # Test single page write (page 10 - safe user data area)
    test_page = 10
    test_data = "DEADBEEF"  # 4 bytes as hex

    print(f"\n1. Testing single page write (page {test_page}, data: {test_data})...")
    resp = requests.post(
        f"{BASE_URL}/readers/{reader_index}/ultralight/{test_page}",
        json={"data": test_data}
    )

    if resp.status_code == 200:
        print(f"   ✅ Single page write SUCCESS")
    else:
        print(f"   ❌ Single page write FAILED: {resp.json()}")
        return False

    # Test read back
    print(f"\n2. Reading back page {test_page}...")
    resp = requests.get(f"{BASE_URL}/readers/{reader_index}/ultralight/{test_page}")

    if resp.status_code == 200:
        result = resp.json()
        read_data = result.get('data', '').upper()
        if read_data == test_data:
            print(f"   ✅ Read back matches: {read_data}")
        else:
            print(f"   ⚠️  Read back differs: got {read_data}, expected {test_data}")
    else:
        print(f"   ❌ Read failed: {resp.json()}")

    # Test batch write (pages 11-13)
    print(f"\n3. Testing batch page write (pages 11-13)...")
    batch_pages = [
        {"page": 11, "data": "11111111"},
        {"page": 12, "data": "22222222"},
        {"page": 13, "data": "33333333"},
    ]

    resp = requests.post(
        f"{BASE_URL}/readers/{reader_index}/ultralight/batch",
        json={"pages": batch_pages}
    )

    if resp.status_code == 200:
        result = resp.json()
        results = result.get('results', [])
        success_count = sum(1 for r in results if r.get('success'))
        print(f"   ✅ Batch write: {success_count}/{len(batch_pages)} pages succeeded")
        for r in results:
            status = "✅" if r.get('success') else "❌"
            error = f" - {r.get('error')}" if r.get('error') else ""
            print(f"      Page {r.get('page')}: {status}{error}")
    else:
        print(f"   ❌ Batch write FAILED: {resp.json()}")
        return False

    # Restore original data (zeros)
    print(f"\n4. Cleaning up (writing zeros to test pages)...")
    cleanup_pages = [
        {"page": 10, "data": "00000000"},
        {"page": 11, "data": "00000000"},
        {"page": 12, "data": "00000000"},
        {"page": 13, "data": "00000000"},
    ]
    resp = requests.post(
        f"{BASE_URL}/readers/{reader_index}/ultralight/batch",
        json={"pages": cleanup_pages}
    )
    if resp.status_code == 200:
        print("   ✅ Cleanup done")

    return True


def test_mifare_classic_write(reader_index=0):
    """Test MIFARE Classic block writes."""
    print("\n=== Testing MIFARE Classic Write ===")

    # Get card info first
    card = get_card(reader_index)
    if not card:
        print("❌ No card detected")
        return False

    print(f"Card detected: {card.get('type', 'Unknown')} (UID: {card.get('uid', 'N/A')})")

    if "Classic" not in card.get('type', ''):
        print(f"⚠️  Card type '{card.get('type')}' is not MIFARE Classic")
        return False

    # Test block write (block 4 - first data block of sector 1, safe to write)
    # Using default transport key FFFFFFFFFFFF
    test_block = 4
    test_data = "00112233445566778899AABBCCDDEEFF"  # 16 bytes as hex
    default_key = "FFFFFFFFFFFF"

    print(f"\n1. Testing block write (block {test_block})...")
    print(f"   Data: {test_data}")
    print(f"   Key: {default_key} (Key A)")

    resp = requests.post(
        f"{BASE_URL}/readers/{reader_index}/mifare/{test_block}",
        json={
            "data": test_data,
            "key": default_key,
            "keyType": "A"
        }
    )

    if resp.status_code == 200:
        print(f"   ✅ Block write SUCCESS")
    else:
        error = resp.json()
        print(f"   ❌ Block write FAILED: {error}")
        return False

    # Test read back
    print(f"\n2. Reading back block {test_block}...")
    resp = requests.get(
        f"{BASE_URL}/readers/{reader_index}/mifare/{test_block}",
        params={"key": default_key, "keyType": "A"}
    )

    if resp.status_code == 200:
        result = resp.json()
        read_data = result.get('data', '').upper()
        if read_data == test_data.upper():
            print(f"   ✅ Read back matches: {read_data}")
        else:
            print(f"   ⚠️  Read back differs: got {read_data}, expected {test_data}")
    else:
        print(f"   ❌ Read failed: {resp.json()}")

    # Restore original data (zeros)
    print(f"\n3. Cleaning up (writing zeros to test block)...")
    resp = requests.post(
        f"{BASE_URL}/readers/{reader_index}/mifare/{test_block}",
        json={
            "data": "00000000000000000000000000000000",
            "key": default_key,
            "keyType": "A"
        }
    )
    if resp.status_code == 200:
        print("   ✅ Cleanup done")

    # Test batch write
    if not test_mifare_classic_batch_write(reader_index):
        return False

    return True


def test_mifare_classic_batch_write(reader_index=0):
    """Test MIFARE Classic batch block writes."""
    print("\n=== Testing MIFARE Classic Batch Write ===")

    default_key = "FFFFFFFFFFFF"

    # Test batch write (blocks 4, 5 in sector 1 and block 8 in sector 2)
    # This tests re-authentication across sector boundaries
    batch_blocks = [
        {"block": 4, "data": "AAAABBBBCCCCDDDDEEEEFFFFAAAABBBB"},
        {"block": 5, "data": "11112222333344445555666677778888"},
        {"block": 8, "data": "DEADBEEFDEADBEEFDEADBEEFDEADBEEF"},  # Different sector
    ]

    print(f"\n1. Testing batch block write (blocks 4, 5, 8 - crosses sectors)...")
    print(f"   Key: {default_key} (Key A)")

    resp = requests.post(
        f"{BASE_URL}/readers/{reader_index}/mifare/batch",
        json={
            "blocks": batch_blocks,
            "key": default_key,
            "keyType": "A"
        }
    )

    if resp.status_code == 200:
        result = resp.json()
        results = result.get('results', [])
        written = result.get('written', 0)
        total = result.get('total', 0)
        print(f"   ✅ Batch write: {written}/{total} blocks succeeded")
        for r in results:
            status = "✅" if r.get('success') else "❌"
            error = f" - {r.get('error')}" if r.get('error') else ""
            print(f"      Block {r.get('block')}: {status}{error}")
    else:
        print(f"   ❌ Batch write FAILED: {resp.json()}")
        return False

    # Verify reads
    print(f"\n2. Verifying written blocks...")
    all_verified = True
    for block_write in batch_blocks:
        block_num = block_write["block"]
        expected = block_write["data"].upper()
        resp = requests.get(
            f"{BASE_URL}/readers/{reader_index}/mifare/{block_num}",
            params={"key": default_key, "keyType": "A"}
        )
        if resp.status_code == 200:
            read_data = resp.json().get('data', '').upper()
            if read_data == expected:
                print(f"   ✅ Block {block_num}: verified")
            else:
                print(f"   ❌ Block {block_num}: mismatch (got {read_data})")
                all_verified = False
        else:
            print(f"   ❌ Block {block_num}: read failed")
            all_verified = False

    # Cleanup: write zeros to all test blocks
    print(f"\n3. Cleaning up (writing zeros to test blocks)...")
    cleanup_blocks = [
        {"block": 4, "data": "00000000000000000000000000000000"},
        {"block": 5, "data": "00000000000000000000000000000000"},
        {"block": 8, "data": "00000000000000000000000000000000"},
    ]
    resp = requests.post(
        f"{BASE_URL}/readers/{reader_index}/mifare/batch",
        json={
            "blocks": cleanup_blocks,
            "key": default_key,
            "keyType": "A"
        }
    )
    if resp.status_code == 200:
        print("   ✅ Cleanup done")

    return all_verified


def main():
    print("NFC Agent Write Test")
    print("=" * 50)

    # Check if agent is running
    try:
        readers = get_readers()
        print(f"Found {len(readers)} reader(s)")
        for i, r in enumerate(readers):
            print(f"  [{i}] {r.get('name', 'Unknown')}")
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to NFC Agent. Is it running?")
        sys.exit(1)

    if not readers:
        print("❌ No readers found")
        sys.exit(1)

    # Get card type to determine which test to run
    card = get_card(0)
    if not card:
        print("\n❌ No card on reader. Please place a card and try again.")
        sys.exit(1)

    card_type = card.get('type', '')
    print(f"\nDetected card type: {card_type}")

    if "NTAG" in card_type or "Ultralight" in card_type:
        success = test_ultralight_write(0)
    elif "Classic" in card_type:
        success = test_mifare_classic_write(0)
    else:
        print(f"\n⚠️  Unknown card type: {card_type}")
        print("Attempting Ultralight test anyway...")
        success = test_ultralight_write(0)

    print("\n" + "=" * 50)
    if success:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
