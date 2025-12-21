#!/bin/bash
# Script to interactively upload files from V3 folder to remote server
# Usage: ./upload_calibration.sh
# 
# This script runs in a loop, prompting you to enter a file path each time.
# Files are uploaded to the remote server, preserving the folder structure.
# SSH connection is kept open to avoid password prompts.

# Configuration
REMOTE_USER="proscout"
REMOTE_HOST="100.74.134.30"
REMOTE_BASE_PATH="/home/proscout/ProScout-master/device-manager"
LOCAL_SOURCE_DIR="V3"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_V3_PATH="${SCRIPT_DIR}/${LOCAL_SOURCE_DIR}"

# SSH ControlMaster settings to keep connection open
SSH_CONTROL_PATH="${HOME}/.ssh/control_%h_%p_%r"
SSH_OPTS="-o ControlMaster=auto -o ControlPath=${SSH_CONTROL_PATH} -o ControlPersist=600"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to upload a single file
upload_file() {
    local file_path="$1"
    
    # Resolve absolute path
    if [[ "$file_path" != /* ]]; then
        # Relative path - check if it's relative to V3 or current directory
        if [[ -f "${LOCAL_V3_PATH}/${file_path}" ]]; then
            file_path="${LOCAL_V3_PATH}/${file_path}"
        elif [[ -f "${SCRIPT_DIR}/${file_path}" ]]; then
            file_path="${SCRIPT_DIR}/${file_path}"
        else
            file_path="${file_path}"
        fi
    fi
    
    # Check if file exists
    if [ ! -f "${file_path}" ]; then
        echo -e "${RED}✗ Error: File not found: ${file_path}${NC}"
        return 1
    fi
    
    # Check if file is within V3 directory
    if [[ "$file_path" != "${LOCAL_V3_PATH}"* ]]; then
        echo -e "${RED}✗ Error: File must be within the V3 directory${NC}"
        echo -e "${YELLOW}  File: ${file_path}${NC}"
        echo -e "${YELLOW}  Expected base: ${LOCAL_V3_PATH}${NC}"
        return 1
    fi
    
    # Calculate relative path from V3
    local relative_path="${file_path#${LOCAL_V3_PATH}/}"
    local remote_dir="${REMOTE_BASE_PATH}/$(dirname "${relative_path}")"
    local remote_file="${REMOTE_BASE_PATH}/${relative_path}"
    
    # Create remote directory if it doesn't exist
    ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '${remote_dir}'" 2>/dev/null
    
    # Upload the file
    echo -e "${CYAN}[$(date +%H:%M:%S)] Uploading: ${relative_path}${NC}"
    rsync -avz --progress -e "ssh ${SSH_OPTS}" \
        "${file_path}" \
        "${REMOTE_USER}@${REMOTE_HOST}:${remote_file}"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Successfully uploaded: ${relative_path}${NC}"
        echo -e "${GREEN}  Remote location: ${remote_file}${NC}"
    else
        echo -e "${RED}✗ Error: Failed to upload ${relative_path}${NC}"
        return 1
    fi
    echo ""
}

# Function to setup SSH connection
setup_ssh_connection() {
    echo -e "${YELLOW}Setting up SSH connection to ${REMOTE_USER}@${REMOTE_HOST}...${NC}"
    
    # Test SSH connection and establish ControlMaster
    ssh ${SSH_OPTS} -o ConnectTimeout=5 \
        "${REMOTE_USER}@${REMOTE_HOST}" "echo 'SSH connection established'" 2>/dev/null
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ SSH connection established and will be kept open${NC}"
    else
        echo -e "${RED}✗ Error: Failed to establish SSH connection${NC}"
        echo -e "${YELLOW}Please ensure SSH key authentication is set up${NC}"
        exit 1
    fi
    echo ""
}

# Function to cleanup SSH connection on exit
cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    # Close SSH ControlMaster connection
    ssh -O exit -o ControlPath=${SSH_CONTROL_PATH} "${REMOTE_USER}@${REMOTE_HOST}" 2>/dev/null
    echo -e "${GREEN}SSH connection closed${NC}"
    exit 0
}

# Trap Ctrl+C and cleanup
trap cleanup SIGINT SIGTERM

# Check if V3 directory exists
if [ ! -d "${LOCAL_V3_PATH}" ]; then
    echo -e "${RED}Error: ${LOCAL_V3_PATH} directory not found!${NC}"
    exit 1
fi

# Setup SSH connection
setup_ssh_connection

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Interactive file uploader${NC}"
echo -e "${BLUE}Source directory: ${LOCAL_V3_PATH}${NC}"
echo -e "${BLUE}Remote base: ${REMOTE_BASE_PATH}${NC}"
echo -e "${BLUE}Enter file path relative to V3 folder (e.g., calibrate/IMU_calibration.py)${NC}"
echo -e "${BLUE}Or enter 'quit'/'exit' to stop${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Interactive loop
while true; do
    echo -e "${YELLOW}Enter file path to upload:${NC} "
    read -r file_input
    
    # Check for exit commands
    if [[ "$file_input" == "quit" || "$file_input" == "exit" || "$file_input" == "q" ]]; then
        break
    fi
    
    # Skip empty input
    if [ -z "$file_input" ]; then
        continue
    fi
    
    # Upload the file
    upload_file "$file_input"
done
