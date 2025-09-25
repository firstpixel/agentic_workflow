#!/usr/bin/env python3
"""
Demo script showcasing the 20 Agentic AI Design Patterns
Run this script to see examples of each pattern in action.

Usage: python demo_patterns.py [pattern_number]
Example: python demo_patterns.py 1  # Run Prompt Chaining demo
         python demo_patterns.py     # Run all patterns
"""

import os
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.core.types import Message, Result
from src.core.utils import to_display

def demo_pattern_1_prompt_chaining():
    """Pattern 1: Prompt Chaining - Sequential task decomposition"""
    print("\n🔗 Pattern 1: Prompt Chaining")
    print("Sequential task decomposition with validation")
    
    # Create agents for each step
    planner = LLMAgent(AgentConfig(
        name="Planner",
        prompt_file="planner/decomposer.md",
        model_config={"model": "llama3.2:latest", "temperature": 0.3}
    ))
    
    writer = LLMAgent(AgentConfig(
        name="Writer", 
        prompt_file="tech_writer.md",
        model_config={"model": "llama3.2:latest", "temperature": 0.7}
    ))
    
    reviewer = LLMAgent(AgentConfig(
        name="Reviewer",
        prompt_file="critic_agent.md", 
        model_config={"model": "llama3.2:latest", "temperature": 0.2}
    ))
    
    # Define sequential workflow
    graph = {
        "Planner": ["Writer"],
        "Writer": ["Reviewer"],
        "Reviewer": []
    }
    
    workflow = WorkflowManager(graph=graph, agents={
        "Planner": planner,
        "Writer": writer, 
        "Reviewer": reviewer
    })
    
    # Execute the chain
    input_data = {"user_prompt": "Create a technical article about machine learning"}
    results = workflow.run_workflow("Planner", input_data)
    result = results[-1] if results else None
    
    print(f"✅ Final result: {to_display(result)}")
    return result

def demo_pattern_2_routing():
    """Pattern 2: Routing - Intelligent request distribution"""
    print("\n🔀 Pattern 2: Routing")
    print("Intelligent request distribution to specialized agents")
    
    from src.agents.switch_agent import SwitchAgent
    
    # Create router and specialized agents
    router = SwitchAgent(AgentConfig(
        name="Router",
        prompt_file="switch_agent.md",
        model_config={
            "model": "llama3.2:latest",
            "temperature": 0.1,
            "routes": {
                "technical": "TechWriter",
                "business": "BizWriter", 
                "creative": "CreativeWriter"
            }
        }
    ))
    
    tech_writer = LLMAgent(AgentConfig(
        name="TechWriter",
        prompt_file="tech_writer.md"
    ))
    
    biz_writer = LLMAgent(AgentConfig(
        name="BizWriter", 
        prompt_file="biz_writer.md"
    ))
    
    creative_writer = LLMAgent(AgentConfig(
        name="CreativeWriter",
        prompt_file="writer_paragraph.md"
    ))
    
    # Test routing
    requests = [
        "Explain quantum computing algorithms",
        "Write a business proposal for AI adoption", 
        "Create a story about time travel"
    ]
    
    for req in requests:
        message = Message(data={"user_prompt": req})
        result = router.execute(message)
        print(f"Request: '{req}' → Routed to: {result.output.get('selected_route', 'Unknown')}")
    
    return True

def demo_pattern_3_parallelization():
    """Pattern 3: Parallelization - Concurrent execution"""
    print("\n⚡ Pattern 3: Parallelization")
    print("Concurrent execution of independent subtasks")
    
    from src.agents.fanout_agent import FanOutAgent
    from src.agents.join_agent import JoinAgent
    
    # Create parallel processing agents
    fanout = FanOutAgent(AgentConfig(name="Fanout"))
    join = JoinAgent(AgentConfig(name="Join"))
    
    # Subtask agents
    summarizer = LLMAgent(AgentConfig(name="Summarizer", prompt_file="planner/summarizer.md"))
    analyzer = LLMAgent(AgentConfig(name="Analyzer", prompt_file="eval_judge.md"))
    keywords = LLMAgent(AgentConfig(name="Keywords", prompt_file="query_rewriter.md"))
    
    # Parallel workflow
    graph = {
        "Fanout": ["Summarizer", "Analyzer", "Keywords"],
        "Summarizer": ["Join"],
        "Analyzer": ["Join"],
        "Keywords": ["Join"], 
        "Join": []
    }
    
    workflow = WorkflowManager(graph=graph, agents={
        "Fanout": fanout,
        "Summarizer": summarizer,
        "Analyzer": analyzer, 
        "Keywords": keywords,
        "Join": join
    })
    
    input_data = {"text": "Artificial intelligence is transforming industries..."}
    results = workflow.run_workflow("Fanout", input_data)
    result = results[-1] if results else None
    
    print(f"✅ Parallel processing complete: {len(result.output.get('results', []))} results combined")
    return result

def demo_pattern_4_reflection():
    """Pattern 4: Reflection - Iterative improvement through criticism"""
    print("\n🪞 Pattern 4: Reflection")
    print("Iterative improvement through criticism and revision")
    
    from src.agents.critic_agent import CriticAgent
    
    writer = LLMAgent(AgentConfig(name="Writer", prompt_file="tech_writer.md"))
    critic = CriticAgent(AgentConfig(name="Critic", prompt_file="critic_agent.md"))
    
    # Reflection loop workflow
    graph = {
        "Writer": ["Critic"],
        "Critic": ["Writer"],  # Creates reflection loop
    }
    
    workflow = WorkflowManager(graph=graph, agents={
        "Writer": writer,
        "Critic": critic
    })
    
    input_data = {"user_prompt": "Write about the ethics of AI"}
    results = workflow.run_workflow("Writer", input_data)
    result = results[-1] if results else None
    
    print(f"✅ Reflection complete after iterations: {result.metrics.get('iterations', 1)}")
    return result

def demo_pattern_5_tool_use():
    """Pattern 5: Tool Use - External tool integration"""
    print("\n🔧 Pattern 5: Tool Use")
    print("External tool integration for specialized capabilities")
    
    from src.agents.tool_runner import ToolRunnerAgent
    
    # Create tool-enabled agent with DuckDuckGo integration
    tool_agent = ToolRunnerAgent(AgentConfig(
        name="ToolRunner",
        model_config={
            "mode": "deterministic", 
            "tools": {
                "duckduckgo": {
                    "enabled": True,
                    "timeout": 10,
                    "delay": 1.0,
                    "max_results_limit": 5,
                    "allow_actions": ["search", "scrape", "search_and_scrape"]
                }
            }
        }
    ))
    
    # Execute tool search
    input_data = {
        "tool": "duckduckgo.search_and_scrape",
        "args": {"query": "latest AI developments 2024", "max_results": 3}
    }
    
    result = tool_agent.execute(Message(data=input_data))
    
    if result.success:
        results = result.output.get('results', [])
        print(f"✅ Tool execution complete: Found {len(results)} results")
        for i, res in enumerate(results[:2], 1):  # Show first 2 results
            print(f"   {i}. {res.get('title', 'No title')}")
    else:
        print(f"❌ Tool execution failed: {result.output}")
    
    return result

def demo_all_patterns():
    """Run demonstrations of all 20 patterns"""
    print("🚀 Agentic AI Framework - 20 Design Patterns Demo")
    print("=" * 60)
    
    patterns = [
        ("1. Prompt Chaining", demo_pattern_1_prompt_chaining),
        ("2. Routing", demo_pattern_2_routing),
        ("3. Parallelization", demo_pattern_3_parallelization), 
        ("4. Reflection", demo_pattern_4_reflection),
        ("5. Tool Use", demo_pattern_5_tool_use),
        # Add more patterns here...
    ]
    
    results = {}
    for name, demo_func in patterns:
        try:
            print(f"\n{'='*20} {name} {'='*20}")
            results[name] = demo_func()
            print(f"✅ {name} completed successfully")
        except Exception as e:
            print(f"❌ {name} failed: {e}")
            results[name] = None
    
    print(f"\n🎉 Demo complete! {sum(1 for r in results.values() if r is not None)}/{len(patterns)} patterns executed successfully")
    return results

def main():
    """Main entry point"""
    # Check if Ollama is available
    try:
        import ollama
        ollama.list()  # Test connection
    except Exception as e:
        print("❌ Ollama not available. Please install and start Ollama:")
        print("   curl -fsSL https://ollama.com/install.sh | sh")
        print("   ollama pull llama3.2:latest")
        return 1
    
    if len(sys.argv) > 1:
        pattern_num = int(sys.argv[1])
        pattern_map = {
            1: demo_pattern_1_prompt_chaining,
            2: demo_pattern_2_routing,
            3: demo_pattern_3_parallelization,
            4: demo_pattern_4_reflection,
            5: demo_pattern_5_tool_use,
        }
        
        if pattern_num in pattern_map:
            pattern_map[pattern_num]()
        else:
            print(f"Pattern {pattern_num} not implemented yet")
    else:
        demo_all_patterns()
    
    return 0

if __name__ == "__main__":
    exit(main())