#!/usr/bin/env bash
# ==============================================================================
# Waveshare RoArm-M1 Environment & Dependencies Setup Script
# ==============================================================================
set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}================================================================${NC}"
echo -e "${CYAN}   🦾 Waveshare RoArm-M1 — Automated Environment Setup          ${NC}"
echo -e "${CYAN}================================================================${NC}"

# Check root vs non-root user for package manager commands
SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo &> /dev/null; then
        SUDO="sudo"
    fi
fi

# 1. Detect OS Package Manager
echo -e "\n${YELLOW}[1/4] Installing system packages & Python Tkinter GUI support...${NC}"
if command -v apt-get &> /dev/null; then
    echo "Detected Debian/Ubuntu Linux system."
    $SUDO apt-get update -y
    $SUDO apt-get install -y python3 python3-pip python3-tk git psmisc
elif command -v dnf &> /dev/null; then
    echo "Detected Fedora/RHEL system."
    $SUDO dnf install -y python3 python3-pip python3-tkinter git psmisc
elif command -v pacman &> /dev/null; then
    echo "Detected Arch Linux system."
    $SUDO pacman -Sy --noconfirm python python-pip tk git psmisc
else
    echo "Package manager not auto-detected. Ensure Python 3 and Tkinter are installed."
fi

# 2. Python Dependencies
echo -e "\n${YELLOW}[2/4] Installing Python dependencies from requirements.txt...${NC}"
python3 -m pip install --upgrade pip 2>/dev/null || true
python3 -m pip install -r requirements.txt

# 3. Serial Port USB Permissions (dialout group)
echo -e "\n${YELLOW}[3/4] Configuring Linux serial USB permissions (dialout group)...${NC}"
if [ -n "$USER" ]; then
    $SUDO usermod -a -G dialout "$USER" 2>/dev/null || true
    echo -e "${GREEN}✓ User '$USER' added to dialout group.${NC}"
fi

# Apply immediate permissions to any currently plugged USB serial devices
if ls /dev/ttyUSB* 1> /dev/null 2>&1 || ls /dev/ttyACM* 1> /dev/null 2>&1; then
    $SUDO chmod 666 /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true
    echo -e "${GREEN}✓ Granted read/write permissions to active /dev/ttyUSB* /dev/ttyACM* ports.${NC}"
fi

# 4. Verification
echo -e "\n${YELLOW}[4/4] Verifying installation...${NC}"
python3 -c "import serial; import tkinter; print('${GREEN}✓ Python pyserial & tkinter successfully verified!${NC}')"

echo -e "\n${GREEN}================================================================${NC}"
echo -e "${GREEN}   🎉 Installation Complete! Ready to Control RoArm-M1          ${NC}"
echo -e "${GREEN}================================================================${NC}"
echo -e "You can now run any of the application studios:"
echo -e "  1. Desktop GUI Studio:       ${CYAN}python3 roarm_gui.py${NC}"
echo -e "  2. Hand-Teaching Sequencer:  ${CYAN}python3 roarm_record_play_gui.py${NC}"
echo -e "  3. Serial Command Studio:    ${CYAN}python3 roarm_serial_console.py${NC}"
echo -e "  4. Physical Motion Demo:     ${CYAN}python3 demos/demo_motions.py${NC}"
echo -e "\n${YELLOW}Note:${NC} If this is your first time adding yourself to the 'dialout' group,"
echo -e "you may need to log out and log back in, or run: ${CYAN}newgrp dialout${NC}"
