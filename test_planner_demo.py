#!/usr/bin/env python3
"""
Simple test script to run the planner demo with real Ollama calls.
This will help us validate the full flows_planner.py integration.
"""

import os
import sys
from src.app.flows_planner import demo_planner

def main():
    print("🚀 Starting Planner Demo with Real Ollama Calls")
    print("=" * 60)
    
    # Set up environment
    if not os.getenv("OLLAMA_MODEL"):
        print("⚠️  No OLLAMA_MODEL set, using default: gemma2:2b")
        os.environ["OLLAMA_MODEL"] = "gemma2:2b"
    
    print(f"Using model: {os.getenv('OLLAMA_MODEL')}")
    print(f"Python version: {sys.version}")
    print()
    
    try:
        # Run the demo
        demo_planner()
        print("\n✅ Demo completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⚠️  Demo interrupted by user")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()