import os, pytest
from pathlib import Path
from src.core.agent import AgentConfig, LLMAgent
from src.core.workflow_manager import WorkflowManager
from src.memory.mongo_stm import MongoSTM
from src.memory.qdrant_store import QdrantVectorStore
from src.memory.memory_manager import MemoryManager
from src.agents.rag_retriever import RAGRetrieverAgent
from tests.test_utils import skip_if_no_ollama, get_test_model_config, skip_if_no_databases

@skip_if_no_ollama()
@skip_if_no_databases()
def test_task5_rag_end_to_end():
    from src.config.settings import get_settings
    settings = get_settings()
    model_config = get_test_model_config("standard", temperature=0.1)
    
    print("🚀 Starting RAG end-to-end test...")
    print("🔧 Using existing prompt files from prompts/ directory...")
    
    # Test Qdrant connection
    try:
        import requests
        qdrant_health = requests.get(f"{settings.qdrant_url}/", timeout=5)  # Use root endpoint instead of /health
        print(f"   Qdrant ({settings.qdrant_url}): {'✅ Connected' if qdrant_health.status_code == 200 else '❌ Connection failed'}")
    except Exception as e:
        print(f"   Qdrant ({settings.qdrant_url}): ❌ Connection error - {e}")
    
    # Test MongoDB connection
    try:
        from pymongo import MongoClient
        mongo_client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
        mongo_client.server_info()  # This will raise an exception if MongoDB is not reachable
        print(f"   MongoDB ({settings.mongo_uri}): ✅ Connected")
        mongo_client.close()
    except Exception as e:
        print(f"   MongoDB ({settings.mongo_uri}): ❌ Connection error - {e}")
    
    # Test Ollama model availability
    try:
        from src.app.main import create_ollama_llm_agent, check_ollama_availability
        if check_ollama_availability(model_config["model"]):
            print(f"   Ollama ({model_config['model']}): ✅ Available")
        else:
            print(f"   Ollama ({model_config['model']}): ❌ Not available")
    except Exception as e:
        print(f"   Ollama ({model_config['model']}): ❌ Error checking availability - {e}")
    
    print("📝 Setting up test environment...")
    
    print("💾 Initializing memory components...")
    
    # memory
    stm = MongoSTM()
    ltm = QdrantVectorStore(collection="test_docs_rag")
    memory = MemoryManager(stm, ltm)

    print("📚 Indexing test documents...")
    # index a few docs
    memory.index_document("Events include page views, taps, custom milestones with timestamps.", meta={"tag":"C1"})
    memory.index_document("Funnels are built from ordered events to measure drop-offs.", meta={"tag":"C2"})

    print("🤖 Setting up agents...")
    retriever = RAGRetrieverAgent(AgentConfig(name="Retriever", model_config={"top_k":2}), memory)
    answerer  = LLMAgent(AgentConfig(name="Answerer", prompt_file="answer_with_context.md", model_config=model_config))

    agents={"Retriever":retriever,"Answerer":answerer}
    graph ={"Retriever":["Answerer"],"Answerer":[]}
    wm=WorkflowManager(graph,agents)

    print("🔍 Running retrieval workflow...")
    question={"query":"How are funnels computed?"}
    r1=wm.run_workflow("Retriever", question)
    print(f"   Retrieval result: {len(r1)} steps, success: {r1[-1].success}")
    print(f"   Final output keys: {list(r1[-1].output.keys())}")
    print(f"   Final output: {r1[-1].output}")
    
    # Check specifically what the Retriever agent returned
    retriever_result = None
    for step in r1:
        if step.output and 'contexts' in step.output:
            retriever_result = step
            break
    
    if retriever_result:
        print(f"   Retriever returned: {len(retriever_result.output.get('contexts', []))} contexts")
        print(f"   Contexts: {retriever_result.output.get('contexts', [])}")
    else:
        print("   No step found with 'contexts' key")
    
    # Check that the overall workflow succeeded
    assert r1[-1].success, "Final workflow step should succeed"
    
    # Check that the Retriever step found contexts
    assert retriever_result is not None, "Should have found retriever step"
    assert isinstance(retriever_result.output.get("contexts"), list), "Contexts should be a list"
    assert len(retriever_result.output["contexts"]) > 0, "Should have retrieved some contexts"

    print("💬 Running answer generation workflow...")
    ctx_md = retriever_result.output["contexts_md"]
    r2=wm.run_workflow("Answerer", {"question":"How are funnels computed?","contexts_md":ctx_md})
    print(f"   Answer result: {len(r2)} steps, success: {r2[-1].success}")
    
    # Confere que veio um texto não vazio
    final_texts=[r.output.get("text") for r in r2 if isinstance(r.output,dict) and "text" in r.output]
    print(f"   Generated texts: {len([t for t in final_texts if t])} non-empty")
    
    assert any(isinstance(t,str) and len(t.strip())>0 for t in final_texts)
    print("✅ RAG end-to-end test completed successfully!")
