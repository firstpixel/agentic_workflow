#!/usr/bin/env python3
"""
Test script to demonstrate interactive EventBus approval.
Run this to test the human-in-the-loop EventBus functionality.
"""

import os
import sys
sys.path.insert(0, os.path.abspath('.'))

from src.app.main import demo_eventbus

if __name__ == "__main__":
    print("🚀 Interactive EventBus Demo")
    print("="*50)
    print("This will prompt you for approval decision.")
    print("You can test the human-in-the-loop EventBus functionality.")
    print("="*50)
    
    # Set environment for testing
    os.environ["PYTHONPATH"] = os.path.abspath('.')
    
    # Run interactive EventBus demo
    demo_eventbus(auto_approve=False)