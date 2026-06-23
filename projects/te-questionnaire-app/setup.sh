#!/bin/bash
# ThousandEyes Questionnaire Automator - Setup Script for macOS

set -e

echo "============================================"
echo " ThousandEyes Questionnaire Automator Setup"
echo "============================================"
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed."
    echo "   Install it from https://www.python.org or via Homebrew: brew install python"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✅ Python $PYTHON_VERSION found"

# Check for pip
if ! python3 -m pip --version &> /dev/null; then
    echo "❌ pip is not available. Installing..."
    python3 -m ensurepip --upgrade
fi

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip --quiet

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "To run the application:"
echo "  source .venv/bin/activate && python main.py"
echo ""
echo "Or use the launch script:"
echo "  ./run.sh"

# Create run script
cat > run.sh << 'EOF'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/.venv/bin/activate"
python "$DIR/main.py"
EOF
chmod +x run.sh

echo "✅ Created run.sh launcher"
