#!/bin/bash

echo "==================================================="
echo "TSPP Clinical Data Extraction - Fast Setup (Unix/Mac)"
echo "==================================================="

# 1. Check and load .env file safely if it exists
if [ -f ".env" ]; then
    # Loads non-comment rows correctly safely escaping spaces
    export $(grep -v '^#' .env | grep -v '^[[:space:]]*$' | xargs)
fi

# 2. Check for GOOGLE_API_KEY
if [ -z "$GOOGLE_API_KEY" ]; then
    echo ""
    echo "[!] GOOGLE_API_KEY is missing."
    read -p "Please enter your GOOGLE_API_KEY: " NEW_KEY
    
    # Save to .env and set in current session
    echo "GOOGLE_API_KEY=$NEW_KEY" >> .env
    export GOOGLE_API_KEY="$NEW_KEY"
    echo "[✓] API Key saved to .env file!"
fi

# 3. Detect Python installation
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "[x] Python is not installed. Please install Python and try again."
    exit 1
fi

# 4. Install dependencies automatically
echo ""
echo "[*] Checking and installing missing dependencies using $PYTHON_CMD..."
$PYTHON_CMD -m pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "[x] Failed to install dependencies. Please ensure pip is installed correctly."
    exit 1
fi

# 5. Run the Frontend App
echo ""
echo "[*] Starting the TSPP Frontend..."
export STREAMLIT_GATHER_USAGE_STATS=false
$PYTHON_CMD -m streamlit run app.py --logger.level=error
