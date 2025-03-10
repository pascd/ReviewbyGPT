#!/bin/bash
# ollama_troubleshoot.sh - Script to diagnose and fix common Ollama issues
# This script helps troubleshoot Ollama API issues, particularly the "exit status 127" error

echo "===== Ollama Troubleshooting Tool ====="
echo

# Check if Ollama is installed
echo "Checking Ollama installation..."
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama is not installed or not in PATH."
    echo "Please install Ollama from https://ollama.com/"
    exit 1
else
    OLLAMA_VERSION=$(ollama --version 2>&1)
    echo "✅ Ollama is installed: $OLLAMA_VERSION"
fi

# Check if Ollama is running
echo
echo "Checking if Ollama service is running..."
if pgrep -x "ollama" > /dev/null; then
    echo "✅ Ollama process is running"
else
    echo "❌ Ollama process is not running"
    echo "Starting Ollama service..."
    ollama serve &
    sleep 3
    echo "Ollama service should now be running in the background"
fi

# Test API connection
echo
echo "Testing API connection..."
API_RESPONSE=$(curl -s -w "\n%{http_code}" http://localhost:11434/api/tags)
HTTP_CODE=$(echo "$API_RESPONSE" | tail -n1)
API_BODY=$(echo "$API_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -eq 200 ]; then
    echo "✅ API connection successful!"
    
    # Parse available models
    echo
    echo "Available models:"
    MODELS=$(echo "$API_BODY" | grep -o '"name":"[^"]*' | sed 's/"name":"//g')
    
    if [ -z "$MODELS" ]; then
        echo "No models found."
    else
        echo "$MODELS"
    fi
else
    echo "❌ API connection failed with status code: $HTTP_CODE"
    echo "Response: $API_BODY"
    echo
    echo "Checking if port 11434 is in use by another application..."
    PORT_STATUS=$(netstat -tuln | grep 11434 || echo "Port not in use")
    echo "$PORT_STATUS"
fi

# Check model installation
echo
echo "Enter the model name you want to use (e.g., mistral, llama3): "
read MODEL_NAME

# Check if the model exists
echo "Checking if model '$MODEL_NAME' is available..."
MODEL_CHECK=$(curl -s "http://localhost:11434/api/tags" | grep -o "\"name\":\"$MODEL_NAME\"" || echo "")

if [ -n "$MODEL_CHECK" ]; then
    echo "✅ Model '$MODEL_NAME' is installed"
else
    echo "❌ Model '$MODEL_NAME' is not installed"
    echo "Would you like to pull this model now? (y/n)"
    read PULL_MODEL
    
    if [ "$PULL_MODEL" = "y" ] || [ "$PULL_MODEL" = "Y" ]; then
        echo "Pulling model '$MODEL_NAME'..."
        ollama pull "$MODEL_NAME"
    fi
fi

# Test the model with a simple prompt
echo
echo "Testing model with a simple prompt..."
TEST_PROMPT="Write a single sentence explaining what systematic reviews are."

echo "Sending test prompt to model $MODEL_NAME..."
TEST_RESPONSE=$(curl -s -X POST http://localhost:11434/api/generate -d "{\"model\":\"$MODEL_NAME\",\"prompt\":\"$TEST_PROMPT\",\"stream\":false}")

if echo "$TEST_RESPONSE" | grep -q "response"; then
    echo "✅ Model test successful!"
    echo "Response preview: $(echo "$TEST_RESPONSE" | grep -o '"response":"[^"]*' | sed 's/"response":"//g' | cut -c 1-100)..."
else
    echo "❌ Model test failed"
    echo "Error: $TEST_RESPONSE"
    
    if echo "$TEST_RESPONSE" | grep -q "exit status 127"; then
        echo
        echo "The 'exit status 127' error typically means the model executable wasn't found."
        echo "This can happen if the model wasn't downloaded correctly or if there are permission issues."
        echo
        echo "Recommended fix:"
        echo "1. Remove the model: ollama rm $MODEL_NAME"
        echo "2. Pull the model again: ollama pull $MODEL_NAME"
        echo "3. Restart Ollama: pkill ollama && ollama serve"
    fi
fi

echo
echo "Memory usage:"
free -h

echo
echo "Disk space:"
df -h | grep -E '/$|/home'

echo
echo "===== Troubleshooting Complete ====="
echo "If you're still experiencing issues, consider:"
echo "1. Using a different model (smaller models like tinyllama may work better)"
echo "2. Checking system resources (some models require substantial RAM)"
echo "3. Reviewing the Ollama logs: ~/.ollama/logs/"
echo "4. Restarting your system and trying again"