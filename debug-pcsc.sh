#!/bin/bash
# NFC Agent PC/SC Debug Script
# Run this script to diagnose NFC reader detection issues

set -e

echo "========================================"
echo "NFC Agent PC/SC Debug Report"
echo "========================================"
echo "Date: $(date)"
echo "Hostname: $(hostname)"
echo ""

# OS Info
echo "=== OS Information ==="
cat /etc/os-release | grep -E "^(NAME|VERSION|ID)="
echo ""

# Check if running in container
echo "=== Container Check ==="
if [ -f /run/.containerenv ]; then
    echo "WARNING: Running inside a container!"
    cat /run/.containerenv
elif [ -f /run/host/container-manager ]; then
    echo "Container manager: $(cat /run/host/container-manager)"
else
    echo "Not running in a container (good)"
fi
echo ""

# USB Devices
echo "=== USB Devices (NFC/Smartcard related) ==="
lsusb 2>/dev/null | grep -iE "(acs|acr|smartcard|card reader|nfc|072f|04e6|076b|1a44)" || echo "No NFC/smartcard USB devices found"
echo ""
echo "All USB devices:"
lsusb 2>/dev/null || echo "lsusb not available"
echo ""

# Check for conflicting kernel modules
echo "=== Kernel NFC Modules (potential conflict!) ==="
if lsmod | grep -qE "(pn533|nfc)"; then
    echo "WARNING: NFC kernel modules are loaded!"
    lsmod | grep -E "(pn533|nfc)"
    echo ""
    echo "These modules may claim your reader before pcscd can access it."
    echo "To fix: sudo modprobe -r pn533_usb pn533 nfc"
    echo "To make permanent: create /etc/modprobe.d/blacklist-pn533.conf with:"
    echo "  blacklist pn533_usb"
    echo "  blacklist pn533"
    echo "  blacklist nfc"
else
    echo "No conflicting NFC kernel modules loaded (good)"
fi
echo ""

# pcscd status
echo "=== pcscd Service Status ==="
systemctl status pcscd --no-pager 2>&1 | head -20 || echo "Could not get pcscd status"
echo ""

# pcscd socket
echo "=== pcscd Socket ==="
ls -la /run/pcscd/ 2>/dev/null || echo "/run/pcscd/ not found - pcscd may not be running"
echo ""

# Installed packages
echo "=== Installed PC/SC Packages ==="
if command -v rpm &>/dev/null; then
    rpm -qa | grep -iE "(pcsc|ccid|scard)" 2>/dev/null || echo "No PC/SC packages found via rpm"
fi
if command -v rpm-ostree &>/dev/null; then
    echo ""
    echo "rpm-ostree layered packages:"
    rpm-ostree status 2>/dev/null | grep -A20 "Layered packages:" | head -25 || echo "No layered packages"
fi
echo ""

# Polkit check
echo "=== Polkit Authorization Test ==="
if command -v pkcheck &>/dev/null; then
    echo "Testing org.debian.pcsc-lite.access_pcsc for current process..."
    if pkcheck --action-id org.debian.pcsc-lite.access_pcsc --process $$ 2>&1; then
        echo "SUCCESS: Current session is authorized for PC/SC access"
    else
        echo "FAILED: Current session is NOT authorized for PC/SC access"
        echo ""
        echo "This is likely the issue! Your session is not recognized as 'active' by polkit."
        echo "Solutions:"
        echo "  1. Run nfc-agent directly from a terminal in your graphical session"
        echo "  2. Use 'nfc-agent install' to set up XDG autostart"
    fi
else
    echo "pkcheck not available"
fi
echo ""

# Session info
echo "=== Session Information ==="
echo "Current user: $(whoami) (UID: $(id -u))"
echo "Groups: $(groups)"
loginctl list-sessions --no-legend 2>/dev/null || echo "loginctl not available"
echo ""
if command -v loginctl &>/dev/null; then
    SESSION_ID=$(loginctl list-sessions --no-legend 2>/dev/null | grep "$(whoami)" | head -1 | awk '{print $1}')
    if [ -n "$SESSION_ID" ]; then
        echo "Session $SESSION_ID details:"
        loginctl show-session "$SESSION_ID" 2>/dev/null | grep -E "^(Active|State|Class|Type|Seat|Remote|Display)=" || true
    fi
fi
echo ""

# pcsc_scan test
echo "=== pcsc_scan Test (5 seconds) ==="
if command -v pcsc_scan &>/dev/null; then
    timeout 5 pcsc_scan 2>&1 || true
else
    echo "pcsc_scan not installed. Install with:"
    echo "  Fedora: sudo dnf install pcsc-tools"
    echo "  Arch: sudo pacman -S pcsc-tools"
    echo "  rpm-ostree: sudo rpm-ostree install pcsc-tools"
fi
echo ""

# Direct scard test using our debug utility
echo "=== Direct PC/SC Connection Test ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/nfc-agent" ]; then
    echo "Testing with nfc-agent binary..."
    timeout 5 "$SCRIPT_DIR/nfc-agent" --no-tray &
    AGENT_PID=$!
    sleep 2

    echo "Querying readers via API:"
    curl -s http://127.0.0.1:32145/v1/readers 2>/dev/null || echo "Could not connect to nfc-agent API"
    echo ""

    echo "Querying logs:"
    curl -s http://127.0.0.1:32145/v1/logs 2>/dev/null | head -50 || echo "Could not get logs"

    kill $AGENT_PID 2>/dev/null || true
else
    echo "nfc-agent binary not found in script directory"
fi
echo ""

# pcscd journal logs
echo "=== Recent pcscd Logs ==="
journalctl -u pcscd --no-pager -n 30 2>/dev/null || echo "Could not get pcscd journal logs"
echo ""

# Summary
echo "========================================"
echo "Debug Summary"
echo "========================================"
echo ""
echo "Common issues and solutions:"
echo ""
echo "1. KERNEL NFC MODULES CONFLICT (most common for ACR122U!)"
echo "   - The pn533_usb module claims the reader before pcscd"
echo "   - Fix: sudo modprobe -r pn533_usb pn533 nfc"
echo "   - Permanent: echo 'blacklist pn533_usb' | sudo tee /etc/modprobe.d/blacklist-pn533.conf"
echo ""
echo "2. NO USB DEVICE DETECTED"
echo "   - Check USB cable and connection"
echo "   - Try a different USB port"
echo "   - Run 'lsusb' to verify device is visible"
echo ""
echo "3. PCSCD NOT RUNNING"
echo "   - Run: sudo systemctl enable --now pcscd"
echo ""
echo "4. POLKIT AUTHORIZATION FAILED"
echo "   - Run nfc-agent from a graphical terminal (not SSH, not a container)"
echo "   - Use 'nfc-agent install' for XDG autostart"
echo ""
echo "5. MISSING DRIVERS (rpm-ostree systems)"
echo "   - Run: sudo rpm-ostree install pcsc-lite pcsc-lite-ccid"
echo "   - Reboot after installation"
echo ""
echo "6. ACS READERS ON ARCH LINUX"
echo "   - Install acsccid from AUR: yay -S acsccid"
echo ""
