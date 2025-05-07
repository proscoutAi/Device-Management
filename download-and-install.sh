#!/bin/bash

# Interactive GCP Authentication Installer for Camera Management
# This script prompts for GCP credentials and handles installation

# Exit on any error
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root or with sudo"
    exit 1
fi

# Configuration
BUCKET_NAME="rpi-installation-script"
OBJECT_PATH="v1.0/Camera Management.zip"
GCS_URL="gs://${BUCKET_NAME}/${OBJECT_PATH}"
BROWSER_URL="https://storage.cloud.google.com/${BUCKET_NAME}/${OBJECT_PATH}"
TEMP_DIR="/tmp/camera-manager-install"
SERVICE_USER="proscout"
CONFIG_DIR="/home/${SERVICE_USER}/camera-manager/config"
GOOGLE_CREDS_FILE="${CONFIG_DIR}/google-credentials.json"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    print_status "Installing Google Cloud SDK..."
    
    # Add Cloud SDK distribution URI as a package source
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list

    # Import Google Cloud public key
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg

    # Update and install Cloud SDK
    apt-get update && apt-get install -y google-cloud-sdk google-cloud-sdk-gke-gcloud-auth-plugin
fi

# Create temp directory
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"
cd "$TEMP_DIR"

# Interactive authentication
print_status "Google Cloud Authentication"
echo "============================="
echo
echo "You need to authenticate with Google Cloud to download the installation files."
echo "Please select how you want to authenticate:"
echo
echo "1. Enter Google Cloud email and password"
echo "2. Use a service account key file"
echo "3. Already authenticated or manual download"
echo
read -p "Select an option (1-3): " AUTH_OPTION

case $AUTH_OPTION in
    1)
        # Email/password authentication
        print_status "Logging in with Google account credentials..."
        echo
        echo "A browser window will open (or you'll receive a link to open on another device)."
        echo "Please follow the instructions to log in with your Google account that has"
        echo "access to the Cloud Storage bucket: ${BUCKET_NAME}"
        echo
        read -p "Press Enter to continue..."
        
        # Start interactive login
        gcloud auth login --no-launch-browser
        
        # Check if login was successful
        if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &>/dev/null; then
            print_error "Authentication failed. Please try again."
            exit 1
        fi
        
        # Show authenticated account
        ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)")
        print_status "Successfully authenticated as: ${ACCOUNT}"
        ;;
    2)
        # Service account key authentication
        print_status "Using service account authentication..."
        echo
        echo "Please provide the path to your service account JSON key file:"
        read -p "Enter path: " KEY_PATH
        
        # Expand tilde if present
        KEY_PATH="${KEY_PATH/#\~/$HOME}"
        
        if [ ! -f "$KEY_PATH" ]; then
            print_error "File not found at: $KEY_PATH"
            exit 1
        fi
        
        # Activate service account
        gcloud auth activate-service-account --key-file="$KEY_PATH"
        
        # Check if login was successful
        if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &>/dev/null; then
            print_error "Authentication failed. Please check your service account key."
            exit 1
        fi
        
        # Show authenticated account
        ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)")
        print_status "Successfully authenticated as: ${ACCOUNT}"
        ;;
    3)
        # Skip authentication
        print_status "Skipping authentication..."
        ;;
    *)
        print_error "Invalid option"
        exit 1
        ;;
esac

# Download the file
print_status "Downloading Camera Management package..."

if [ "$AUTH_OPTION" -eq 3 ]; then
    # Manual download path
    print_status "Please provide the path to the ZIP file you downloaded manually:"
    read -p "Enter path: " MANUAL_PATH
    
    # Expand tilde if present
    MANUAL_PATH="${MANUAL_PATH/#\~/$HOME}"
    
    if [ ! -f "$MANUAL_PATH" ]; then
        print_error "File not found at: $MANUAL_PATH"
        exit 1
    fi
    
    cp "$MANUAL_PATH" "Camera Management.zip"
    print_status "File copied successfully!"
else
    # Try downloading with gsutil
    if gsutil cp "${GCS_URL}" "Camera Management.zip"; then
        print_status "Download successful using gsutil!"
    else
        print_warning "gsutil download failed. Listing available files in bucket..."
        gsutil ls "gs://${BUCKET_NAME}/"
        
        print_status "Since automatic download failed, please download the file manually from:"
        echo "${BROWSER_URL}"
        echo
        print_status "Please provide the path to the ZIP file you downloaded manually:"
        read -p "Enter path: " MANUAL_PATH
        
        # Expand tilde if present
        MANUAL_PATH="${MANUAL_PATH/#\~/$HOME}"
        
        if [ ! -f "$MANUAL_PATH" ]; then
            print_error "File not found at: $MANUAL_PATH"
            exit 1
        fi
        
        cp "$MANUAL_PATH" "Camera Management.zip"
        print_status "File copied successfully!"
    fi
fi

# Verify the ZIP file
print_status "Verifying downloaded ZIP file..."
if ! unzip -t "Camera Management.zip" &>/dev/null; then
    print_error "The file doesn't appear to be a valid ZIP file"
    exit 1
fi

# Extract the ZIP file
print_status "Extracting ZIP file..."
unzip -q "Camera Management.zip"

# Remove Mac-specific files
find . -name ".DS_Store" -delete
find . -name "._*" -delete
rm -rf "__MACOSX"

# Find the install script
print_status "Looking for install script..."
INSTALL_SCRIPT=$(find . -name "install.sh" -type f | grep -v "__MACOSX" | head -1)

if [ -n "$INSTALL_SCRIPT" ]; then
    print_status "Found install script at: $INSTALL_SCRIPT"
    chmod +x "$INSTALL_SCRIPT"
    
    # Change to the directory containing install.sh
    cd "$(dirname "$INSTALL_SCRIPT")"
    
    # Save authentication for the camera application
    mkdir -p "$(dirname "$GOOGLE_CREDS_FILE")"
    
    if [ "$AUTH_OPTION" -eq 2 ]; then
        # Copy service account key for the camera application
        cp "$KEY_PATH" "$GOOGLE_CREDS_FILE"
        chmod 600 "$GOOGLE_CREDS_FILE"
        chown ${SERVICE_USER}:${SERVICE_USER} "$GOOGLE_CREDS_FILE"
        print_status "Service account key saved for the camera application"
    else
        # Create a dedicated service account for the camera application
        print_status "Creating a dedicated service account for the camera application..."
        
        # Get current project ID
        PROJECT_ID=$(gcloud config get-value project)
        
        if [ -z "$PROJECT_ID" ]; then
            print_warning "Could not determine project ID. Setting up authentication for the camera application may fail."
        else
            SERVICE_ACCOUNT_NAME="camera-manager-service"
            
            # Check if service account already exists
            if ! gcloud iam service-accounts describe "${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" &>/dev/null; then
                print_status "Creating service account: ${SERVICE_ACCOUNT_NAME}"
                gcloud iam service-accounts create "${SERVICE_ACCOUNT_NAME}" \
                    --description="Service account for Raspberry Pi Camera Manager" \
                    --display-name="Camera Manager Service Account"
                
                # Grant necessary permissions
                print_status "Granting storage permissions..."
                gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
                    --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
                    --role="roles/storage.objectCreator"
                
                gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
                    --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
                    --role="roles/storage.objectViewer"
            else
                print_status "Service account already exists: ${SERVICE_ACCOUNT_NAME}"
            fi
            
            # Create a service account key
            print_status "Creating service account key..."
            mkdir -p "$(dirname "$GOOGLE_CREDS_FILE")"
            gcloud iam service-accounts keys create "$GOOGLE_CREDS_FILE" \
                --iam-account="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
            
            # Set proper permissions for the key file
            chmod 600 "$GOOGLE_CREDS_FILE"
            chown ${SERVICE_USER}:${SERVICE_USER} "$GOOGLE_CREDS_FILE"
        fi
    fi
    
    # Run the installation
    print_status "Running installation script..."
    ./install.sh
else
    print_error "install.sh not found in the package"
    print_status "Directory contents:"
    find . -type f | grep -v "__MACOSX" | head -20
    exit 1
fi

# Cleanup
cd /
rm -rf "$TEMP_DIR"

print_status "Installation complete!"