#!/bin/bash
# CUDA Installation Guide for Ollama
# This script guides you through installing CUDA for Ollama GPU acceleration

echo "===== CUDA Installation Guide for Ollama ====="
echo "This guide will help you install CUDA libraries needed for Ollama GPU acceleration."
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script with sudo permissions to install packages."
    echo "Usage: sudo bash cuda_install.sh"
    exit 1
fi

# Check OS
echo "Detecting operating system..."
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    VER=$VERSION_ID
    echo "Detected: $OS $VER"
else
    echo "Could not detect OS. This script supports Ubuntu, Debian, and similar distributions."
    exit 1
fi

# Check if GPU is present
echo
echo "Checking for NVIDIA GPU..."
if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU detected!"
    nvidia-smi | head -n 10
else
    echo "NVIDIA GPU not detected or drivers not installed."
    echo "You need an NVIDIA GPU with proper drivers to use GPU acceleration."
    echo
    echo "To install NVIDIA drivers:"
    echo "  Ubuntu: sudo ubuntu-drivers autoinstall"
    echo "  Debian: apt install nvidia-driver"
    echo
    echo "After installing drivers, reboot your system and run this script again."
    exit 1
fi

# Check which version of Ollama is installed
echo
echo "Checking Ollama installation..."
OLLAMA_SNAP=false

if command -v ollama &> /dev/null; then
    echo "Ollama is installed."
    OLLAMA_PATH=$(which ollama)
    echo "Ollama path: $OLLAMA_PATH"
    
    if [[ $OLLAMA_PATH == /snap/* ]]; then
        echo "Ollama is installed via Snap."
        OLLAMA_SNAP=true
    else
        echo "Ollama is installed via traditional package."
    fi
    
    # Get Ollama version
    OLLAMA_VERSION=$(ollama --version 2>&1)
    echo "Ollama version: $OLLAMA_VERSION"
else
    echo "Ollama is not installed. Please install Ollama first."
    echo "Visit https://ollama.com/ for installation instructions."
    exit 1
fi

# Install CUDA libraries based on installation type
echo
echo "Installing required CUDA libraries..."

if [ "$OLLAMA_SNAP" = true ]; then
    echo "For Snap installation of Ollama, we need to install specific CUDA libraries:"
    apt-get update
    apt-get install -y libcudart12
    echo "Installed libcudart12 for Snap Ollama."
else
    echo "For traditional Ollama installation, installing full CUDA toolkit:"
    if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
        apt-get update
        apt-get install -y nvidia-cuda-toolkit
        echo "Installed CUDA toolkit."
    else
        echo "Could not determine appropriate CUDA installation for your OS."
        echo "Please manually install CUDA toolkit."
        exit 1
    fi
fi

# Verify CUDA installation
echo
echo "Verifying CUDA installation..."
if ldconfig -p | grep -q "libcudart"; then
    echo "CUDA libraries found!"
    ldconfig -p | grep "libcudart"
else
    echo "CUDA libraries not found in system paths."
    echo "Installation may not have completed successfully."
    exit 1
fi

# Test Ollama with a simple GPU model
echo
echo "Testing Ollama with GPU..."
echo "Pulling a small test model (if not already installed)..."
ollama pull tinyllama:latest

echo 
echo "Testing model with GPU acceleration..."
RESULT=$(curl -s -X POST http://localhost:11434/api/generate -d '{
  "model": "tinyllama:latest",
  "prompt": "Say hello world",
  "stream": false,
  "options": {
    "num_gpu": 99
  }
}')

if [[ $RESULT == *"error"* ]]; then
    echo "Error using GPU acceleration:"
    echo $RESULT
    echo 
    echo "You may need to restart Ollama for changes to take effect:"
    echo "sudo systemctl restart ollama"
    echo "or"
    echo "pkill ollama && ollama serve"
else
    echo "Test successful! GPU acceleration is working."
    echo "Response: $(echo $RESULT | grep -o '"response":"[^"]*' | sed 's/"response":"//')"
fi

echo
echo "===== CUDA Installation Complete ====="
echo "If you encountered any issues, please try the following:"
echo "1. Restart Ollama: sudo systemctl restart ollama"
echo "2. Restart your computer"
echo "3. Verify your NVIDIA drivers are properly installed"
echo
echo "For troubleshooting, check the Ollama logs:"
echo "~/.ollama/logs/ollama.log"