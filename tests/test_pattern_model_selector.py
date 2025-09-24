import os, pytest
from pathlib import Path

from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.agents.model_selector import ModelSelectorAgent
from tests.test_utils import skip_if_no_ollama, get_test_model_config

@skip_if_no_ollama()
def test_task9_model_selector_applies_overrides(tmp_path, monkeypatch):
    # Get the three different model configurations from settings
    simple_config = get_test_model_config("simple", temperature=0.1)
    standard_config = get_test_model_config("standard", temperature=0.3)  
    complex_config = get_test_model_config("complex", temperature=0.6)
    
    # Extract model names for the three different complexity levels
    model1 = simple_config["model"]    # Simple tasks
    model2 = standard_config["model"]  # Standard tasks  
    model3 = complex_config["model"]   # Complex tasks
    
    # Use the actual prompts folder instead of creating temporary ones
    # The PROMPT_DIR environment variable should point to the real prompts directory
    
    # Router with classes mapping using 3 different models - use model2 for better instruction following
    router = ModelSelectorAgent(AgentConfig(
        name="ModelSelector",
        prompt_file="model_router.md",  # Use the actual prompt file from prompts folder
        model_config={
            "model": model1,  # Use the 3b model for better instruction following
            "options": {"temperature": 0.0},
            "classes": {
                "SIMPLE":   {"model": model1, "options": {"temperature": 0.1}},
                "STANDARD": {"model": model2, "options": {"temperature": 0.3}},
                "COMPLEX":  {"model": model3, "options": {"temperature": 0.6}}
            },
            "targets": ["Writer"]
        }
    ))

    # Writer starts with model1, will be overridden by selector to other models based on complexity
    writer = LLMAgent(AgentConfig(
        name="Writer",
        prompt_file="tech_writer.md",
        model_config={"model": model1, "options": {"temperature": 0.0}}
    ))

    agents = {"ModelSelector": router, "Writer": writer}
    graph  = {"ModelSelector": ["Writer"], "Writer": []}
    wm = WorkflowManager(graph, agents)

    # Test SIMPLE complexity - very basic task
    user_text = {"text": "Write one sentence summary. [[SIMPLE]]"}
    results = wm.run_workflow("ModelSelector", user_text)

    # Writer should have been executed and used; ensure it produced text
    final_texts = [r.output.get("text") for r in results if isinstance(r.output, dict) and "text" in r.output]
    assert any(isinstance(t, str) and len(t.strip()) > 0 for t in final_texts), "No text output generated"

    # Check that Writer's model_config was overridden
    assert isinstance(writer.config.model_config, dict)

    # The configuration should have changed to SIMPLE settings
    current_temp = writer.config.model_config.get("options", {}).get("temperature")
    current_model = writer.config.model_config.get("model")

    # For SIMPLE: should be model1 with temp 0.1
    assert current_model == model1, f"Expected {model1}, got {current_model}"
    assert current_temp == 0.1, f"Expected temp 0.1, got {current_temp}"
    print(f"✅ SIMPLE test - Applied: model={current_model}, temp={current_temp}")    # Reset writer config for next test
    writer.config.model_config = {"model": model1, "options": {"temperature": 0.0}}
    
    # Test STANDARD complexity - more detailed task
    user_text = {"text": "Analyze and explain the design patterns used in this system. [[STANDARD]]"}
    results = wm.run_workflow("ModelSelector", user_text)
    
    # Verify the routing mechanism selected STANDARD
    current_temp = writer.config.model_config.get("options", {}).get("temperature")
    current_model = writer.config.model_config.get("model")
    
    # For STANDARD: should be model2 with temp 0.3
    assert current_model == model2, f"Expected {model2}, got {current_model}"
    assert current_temp == 0.3, f"Expected temp 0.3, got {current_temp}"
    print(f"✅ STANDARD test - Applied: model={current_model}, temp={current_temp}")
    
    # Reset writer config for next test  
    writer.config.model_config = {"model": model1, "options": {"temperature": 0.0}}
    
    # Test COMPLEX complexity - architectural task
    user_text = {"text": "[[COMPLEX]] Design microservices architecture"}
    results = wm.run_workflow("ModelSelector", user_text)
    
    # Verify the routing mechanism selected COMPLEX
    current_temp = writer.config.model_config.get("options", {}).get("temperature")
    current_model = writer.config.model_config.get("model")
    
    # For COMPLEX: should be model3 with temp 0.6
    assert current_model == model3, f"Expected {model3}, got {current_model}"
    assert current_temp == 0.6, f"Expected temp 0.6, got {current_temp}"
    print(f"✅ COMPLEX test - Applied: model={current_model}, temp={current_temp}")
    
    # Verify that at least one of the three classes (SIMPLE, STANDARD, COMPLEX) is properly configured
    simple_config = router.classes.get("SIMPLE", {})
    standard_config = router.classes.get("STANDARD", {})
    complex_config = router.classes.get("COMPLEX", {})
    
    assert simple_config.get("model") == model1
    assert standard_config.get("model") == model2  
    assert complex_config.get("model") == model3
    assert simple_config.get("options", {}).get("temperature") == 0.1
    assert standard_config.get("options", {}).get("temperature") == 0.3
    assert complex_config.get("options", {}).get("temperature") == 0.6
