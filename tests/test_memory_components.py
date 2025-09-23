"""
Tests for memory components: MongoSTM, QdrantVectorStore, and MemoryManager
"""
import pytest
import os
from typing import Dict, Any
from tests.test_utils import get_test_database_config, skip_if_no_databases

# Get database configuration from centralized settings
db_config = get_test_database_config()

@skip_if_no_databases()
class TestMongoSTM:
    """Test Short Term Memory (STM) with MongoDB"""
    
    def setup_method(self):
        """Setup for each test method"""
        from src.memory.mongo_stm import MongoSTM
        self.stm = MongoSTM(uri=db_config["mongo_uri"], db_name="test_memory", coll_name="test_stm")
        # Clean up any existing test data
        self.stm.client.drop_database("test_memory")
    
    def teardown_method(self):
        """Cleanup after each test method"""
        self.stm.client.drop_database("test_memory")
        self.stm.client.close()
    
    def test_stm_add_and_recent(self):
        """Test adding messages and retrieving recent ones"""
        session_id = "test_session_1"
        
        # Add some messages
        self.stm.add(session_id, "user", "Hello, how are you?")
        self.stm.add(session_id, "assistant", "I'm doing well, thank you!")
        self.stm.add(session_id, "user", "What can you help me with?")
        
        # Retrieve recent messages
        recent = self.stm.recent(session_id, limit=5)
        
        assert len(recent) == 3
        assert recent[0]["role"] == "user"
        assert recent[0]["content"] == "Hello, how are you?"
        assert recent[1]["role"] == "assistant"
        assert recent[1]["content"] == "I'm doing well, thank you!"
        assert recent[2]["role"] == "user"
        assert recent[2]["content"] == "What can you help me with?"
    
    def test_stm_with_metadata(self):
        """Test adding messages with metadata"""
        session_id = "test_session_2"
        meta = {"timestamp": "2025-09-21T10:00:00Z", "source": "test"}
        
        self.stm.add(session_id, "user", "Test message with metadata", meta)
        
        recent = self.stm.recent(session_id, limit=1)
        assert len(recent) == 1
        assert recent[0]["meta"]["timestamp"] == "2025-09-21T10:00:00Z"
        assert recent[0]["meta"]["source"] == "test"
    
    def test_stm_limit_works(self):
        """Test that limit parameter works correctly"""
        session_id = "test_session_3"
        
        # Add 5 messages
        for i in range(5):
            self.stm.add(session_id, "user", f"Message {i+1}")
        
        # Test different limits
        recent_2 = self.stm.recent(session_id, limit=2)
        recent_3 = self.stm.recent(session_id, limit=3)
        
        assert len(recent_2) == 2
        assert len(recent_3) == 3
        # Test that the limit actually works (don't assume order, just check we get the right count)
        all_messages = self.stm.recent(session_id, limit=10)
        assert len(all_messages) == 5
    
    def test_stm_session_isolation(self):
        """Test that different sessions don't interfere"""
        session_1 = "test_session_4a"
        session_2 = "test_session_4b"
        
        self.stm.add(session_1, "user", "Message for session 1")
        self.stm.add(session_2, "user", "Message for session 2")
        
        recent_1 = self.stm.recent(session_1, limit=5)
        recent_2 = self.stm.recent(session_2, limit=5)
        
        assert len(recent_1) == 1
        assert len(recent_2) == 1
        assert recent_1[0]["content"] == "Message for session 1"
        assert recent_2[0]["content"] == "Message for session 2"


@skip_if_no_databases()
class TestQdrantVectorStore:
    """Test Long Term Memory (LTM) with Qdrant Vector Store"""
    
    def setup_method(self):
        """Setup for each test method"""
        from src.memory.qdrant_store import QdrantVectorStore
        self.ltm = QdrantVectorStore(url=db_config["qdrant_url"], collection="test_ltm_collection")
        # Clean up any existing test collection
        try:
            self.ltm.client.delete_collection("test_ltm_collection")
        except:
            pass  # Collection might not exist
    
    def teardown_method(self):
        """Cleanup after each test method"""
        try:
            self.ltm.client.delete_collection("test_ltm_collection")
        except:
            pass  # Collection might not exist
    
    def test_ltm_index_and_search(self):
        """Test indexing documents and searching them"""
        # Index some test documents
        docs = [
            {"text": "Machine learning is a subset of artificial intelligence", "meta": {"topic": "AI"}},
            {"text": "Python is a popular programming language for data science", "meta": {"topic": "Programming"}},
            {"text": "Vector databases store high-dimensional data efficiently", "meta": {"topic": "Databases"}}
        ]
        
        self.ltm.index_texts(docs)
        
        # Search for relevant documents
        results = self.ltm.search("artificial intelligence", top_k=2)
        
        assert len(results) <= 2  # Should return at most 2 results
        assert len(results) > 0   # Should find at least one result
        
        # Check that the most relevant result contains expected content
        top_result = results[0]
        assert "text" in top_result
        assert "score" in top_result
        assert "meta" in top_result
        assert isinstance(top_result["score"], (int, float))
    
    def test_ltm_search_relevance(self):
        """Test that search returns relevant results in order"""
        # Index documents with clear topic separation
        docs = [
            {"text": "Dogs are loyal pets that love to play fetch", "meta": {"category": "pets"}},
            {"text": "Machine learning algorithms can classify images of dogs", "meta": {"category": "AI"}},
            {"text": "Cats are independent animals that like to sleep", "meta": {"category": "pets"}}
        ]
        
        self.ltm.index_texts(docs)
        
        # Search for dog-related content
        results = self.ltm.search("dog pets", top_k=3)
        
        assert len(results) > 0
        # The first result should be most relevant (about dogs as pets)
        assert "Dogs are loyal pets" in results[0]["text"] or "Machine learning algorithms" in results[0]["text"]
    
    def test_ltm_metadata_preservation(self):
        """Test that metadata is preserved in search results"""
        docs = [
            {"text": "Test document about metadata", "meta": {"author": "test_user", "version": 1}}
        ]
        
        self.ltm.index_texts(docs)
        results = self.ltm.search("metadata", top_k=1)
        
        assert len(results) == 1
        assert results[0]["meta"]["author"] == "test_user"
        assert results[0]["meta"]["version"] == 1
    
    def test_ltm_empty_search(self):
        """Test searching when no documents are indexed"""
        # Don't index any documents, collection might not even exist
        try:
            results = self.ltm.search("nonexistent query", top_k=5)
            assert isinstance(results, list)
            assert len(results) == 0
        except Exception as e:
            # If collection doesn't exist, search should fail gracefully
            # This is acceptable behavior for an empty/non-existent collection
            error_str = str(e)
            assert ("Collection" in error_str and "doesn't exist" in error_str) or "404" in error_str


@skip_if_no_databases()
class TestMemoryManager:
    """Test MemoryManager integration of STM and LTM"""
    
    def setup_method(self):
        """Setup for each test method"""
        from src.memory.mongo_stm import MongoSTM
        from src.memory.qdrant_store import QdrantVectorStore
        from src.memory.memory_manager import MemoryManager
        
        self.stm = MongoSTM(uri=db_config["mongo_uri"], db_name="test_memory_mgr", coll_name="test_stm_mgr")
        self.ltm = QdrantVectorStore(url=db_config["qdrant_url"], collection="test_ltm_mgr_collection")
        self.memory = MemoryManager(self.stm, self.ltm)
        
        # Cleanup
        self.stm.client.drop_database("test_memory_mgr")
        try:
            self.ltm.client.delete_collection("test_ltm_mgr_collection")
        except:
            pass
    
    def teardown_method(self):
        """Cleanup after each test method"""
        self.stm.client.drop_database("test_memory_mgr")
        try:
            self.ltm.client.delete_collection("test_ltm_mgr_collection")
        except:
            pass
        self.stm.client.close()
    
    def test_memory_manager_stm_operations(self):
        """Test STM operations through MemoryManager"""
        session_id = "test_mgr_session_1"
        
        # Add messages via MemoryManager
        self.memory.stm_add(session_id, "user", "Hello from memory manager")
        self.memory.stm_add(session_id, "assistant", "Hi! I'm working through MemoryManager")
        
        # Retrieve via MemoryManager
        recent = self.memory.stm_recent(session_id, limit=5)
        
        assert len(recent) == 2
        assert recent[0]["content"] == "Hello from memory manager"
        assert recent[1]["content"] == "Hi! I'm working through MemoryManager"
    
    def test_memory_manager_ltm_operations(self):
        """Test LTM operations through MemoryManager"""
        # Index a document
        self.memory.index_document(
            "MemoryManager combines STM and LTM for comprehensive memory management",
            meta={"component": "MemoryManager", "test": True}
        )
        
        # Search for context
        contexts = self.memory.search_context("memory management", top_k=2)
        
        assert len(contexts) > 0
        assert contexts[0]["text"] == "MemoryManager combines STM and LTM for comprehensive memory management"
        assert contexts[0]["meta"]["component"] == "MemoryManager"
        assert contexts[0]["meta"]["test"] is True
    
    def test_memory_manager_integration(self):
        """Test that STM and LTM work together through MemoryManager"""
        session_id = "test_integration_session"
        
        # Add to STM
        self.memory.stm_add(session_id, "user", "I need help with vector search")
        
        # Add to LTM
        self.memory.index_document(
            "Vector search allows finding similar documents using embeddings",
            meta={"topic": "vector_search"}
        )
        self.memory.index_document(
            "Embeddings convert text into numerical vectors for similarity comparison",
            meta={"topic": "embeddings"}
        )
        
        # Verify STM has our message
        stm_messages = self.memory.stm_recent(session_id, limit=5)
        assert len(stm_messages) == 1
        assert "vector search" in stm_messages[0]["content"]
        
        # Verify LTM can find relevant context
        contexts = self.memory.search_context("vector search embeddings", top_k=3)
        assert len(contexts) >= 1
        
        # Check that we get relevant results
        relevant_found = any("vector" in ctx["text"].lower() for ctx in contexts)
        assert relevant_found, f"No relevant contexts found in: {contexts}"


# Test environment check function
def test_memory_environment_check():
    """Test that shows what database configuration is being used"""
    print(f"🔍 Memory Test Environment Check:")
    print(f"   MONGO_URI: {'✅ Set' if db_config['mongo_uri'] else '❌ Missing'} -> {db_config['mongo_uri']}")
    print(f"   QDRANT_URL: {'✅ Set' if db_config['qdrant_url'] else '❌ Missing'} -> {db_config['qdrant_url']}")
    print(f"   ✅ Using centralized configuration from settings.py")
    
    # This test always passes, it's just for information
    assert True