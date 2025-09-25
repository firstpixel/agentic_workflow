#!/bin/bash

# Agentic Workflow Demo Runner
# This script activates the virtual environment and runs the demos

echo "🚀 Agentic AI Workflow Framework Demo"
echo "======================================"

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please create one with:"
    echo "   python -m venv .venv"
    echo "   source .venv/bin/activate" 
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Check if ollama package is available
if ! python -c "import ollama" 2>/dev/null; then
    echo "❌ Ollama package not found. Installing..."
    pip install ollama
fi

# Check if Ollama service is running
if ! ollama list >/dev/null 2>&1; then
    echo "❌ Ollama service not running. Please start it with:"
    echo "   ollama serve"
    exit 1
fi

echo "✅ Environment ready!"
echo ""

# Run the demo
if [ $# -eq 0 ]; then
    echo "Available demos:"
    echo "  1. Pattern demos (requires Ollama): ./run_demo.sh patterns"
    echo "  2. Code executor (no LLM needed): ./run_demo.sh executor"
    echo "  3. Specific pattern: ./run_demo.sh [pattern_number]"
    echo ""
    echo "Running pattern demos..."
    python demo_patterns.py
elif [ "$1" = "executor" ]; then
    echo "Running code executor demo (no LLM required)..."
    python demo_code_executor.py
elif [ "$1" = "patterns" ]; then
    echo "Running all pattern demos..."
    python demo_patterns.py
else
    echo "Running pattern $1..."
    python demo_patterns.py $1
fi