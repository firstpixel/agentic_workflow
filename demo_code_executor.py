#!/usr/bin/env python3
"""
Demo script to test CodeExecutorAgent functionality without requiring Ollama

This script demonstrates the core functionality of the CodeExecutorAgent
by mocking the LLM responses to simulate code generation and execution.
"""

import os
import sys
import json
from pathlib import Path
from unittest.mock import patch

# Ensure the project root is in sys.path for src imports
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from src.agents.code_executor_agent import CodeExecutorAgent
from src.core.agent import AgentConfig
from src.core.types import Message, Result


def create_demo_agent(project_name: str = "demo_project") -> CodeExecutorAgent:
    """Create a CodeExecutorAgent for demonstration"""
    output_dir = Path("./demo_output") / project_name
    
    config = AgentConfig(
        name="DemoCodeExecutor",
        prompt_file="code_executor.md",
        model_config={
            "project_root": str(output_dir),
            "enable_execution": True,
            "allowed_extensions": [".py", ".js", ".html", ".css", ".md", ".txt", ".json"]
        }
    )
    
    return CodeExecutorAgent(config)


def mock_llm_response_python_calculator():
    """Mock LLM response for Python calculator project"""
    return {
        "files": [
            {
                "path": "calculator.py",
                "content": '''"""
Simple Calculator Module
Provides basic arithmetic operations
"""

class Calculator:
    """A simple calculator class"""
    
    def __init__(self):
        self.history = []
    
    def add(self, a, b):
        """Add two numbers"""
        result = a + b
        self.history.append(f"{a} + {b} = {result}")
        return result
    
    def subtract(self, a, b):
        """Subtract b from a"""
        result = a - b
        self.history.append(f"{a} - {b} = {result}")
        return result
    
    def multiply(self, a, b):
        """Multiply two numbers"""
        result = a * b
        self.history.append(f"{a} * {b} = {result}")
        return result
    
    def divide(self, a, b):
        """Divide a by b"""
        if b == 0:
            raise ValueError("Cannot divide by zero")
        result = a / b
        self.history.append(f"{a} / {b} = {result}")
        return result
    
    def get_history(self):
        """Get calculation history"""
        return self.history.copy()
    
    def clear_history(self):
        """Clear calculation history"""
        self.history.clear()


if __name__ == "__main__":
    calc = Calculator()
    
    print("Python Calculator Demo")
    print("=" * 30)
    
    # Demo calculations
    print(f"2 + 3 = {calc.add(2, 3)}")
    print(f"10 - 4 = {calc.subtract(10, 4)}")
    print(f"5 * 6 = {calc.multiply(5, 6)}")
    print(f"15 / 3 = {calc.divide(15, 3)}")
    
    print("\\nCalculation History:")
    for entry in calc.get_history():
        print(f"  {entry}")
''',
                "language": "python",
                "description": "Complete calculator implementation with history tracking"
            },
            {
                "path": "README.md",
                "content": '''# Python Calculator

A simple calculator implementation in Python with the following features:

## Features
- Basic arithmetic operations (add, subtract, multiply, divide)
- Calculation history tracking
- Error handling for division by zero
- Clean object-oriented design

## Usage

```python
from calculator import Calculator

calc = Calculator()

# Perform calculations
result = calc.add(5, 3)        # Returns 8
result = calc.subtract(10, 2)  # Returns 8
result = calc.multiply(4, 3)   # Returns 12
result = calc.divide(15, 3)    # Returns 5.0

# View history
history = calc.get_history()
print(history)

# Clear history
calc.clear_history()
```

## Running the Demo

```bash
python calculator.py
```

This will run a demonstration of all calculator functions.
''',
                "language": "markdown",
                "description": "Documentation for the calculator project"
            }
        ],
        "scripts": [
            {
                "language": "bash",
                "code": '''#!/bin/bash
echo "Setting up Python Calculator project..."

# Create project structure
mkdir -p tests docs

# Create __init__.py for package structure
touch __init__.py
touch tests/__init__.py

# Create a simple test file
cat > tests/test_calculator.py << 'EOF'
import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calculator import Calculator

class TestCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()
    
    def test_add(self):
        self.assertEqual(self.calc.add(2, 3), 5)
        self.assertEqual(self.calc.add(-1, 1), 0)
    
    def test_subtract(self):
        self.assertEqual(self.calc.subtract(5, 3), 2)
        self.assertEqual(self.calc.subtract(0, 5), -5)
    
    def test_multiply(self):
        self.assertEqual(self.calc.multiply(3, 4), 12)
        self.assertEqual(self.calc.multiply(-2, 3), -6)
    
    def test_divide(self):
        self.assertEqual(self.calc.divide(8, 2), 4)
        self.assertEqual(self.calc.divide(7, 2), 3.5)
    
    def test_divide_by_zero(self):
        with self.assertRaises(ValueError):
            self.calc.divide(5, 0)
    
    def test_history(self):
        self.calc.add(1, 2)
        self.calc.multiply(3, 4)
        history = self.calc.get_history()
        self.assertEqual(len(history), 2)
        self.assertIn("1 + 2 = 3", history)
        self.assertIn("3 * 4 = 12", history)

if __name__ == '__main__':
    unittest.main()
EOF

echo "Python Calculator project setup complete!"
echo "Files created:"
echo "  - calculator.py (main implementation)"
echo "  - tests/test_calculator.py (unit tests)"
echo "  - README.md (documentation)"
echo ""
echo "To run tests: python -m unittest tests.test_calculator"
echo "To run demo: python calculator.py"
''',
                "description": "Setup script for Python calculator project structure and tests"
            }
        ],
        "tests": [
            {
                "type": "python",
                "file": "calculator.py",
                "description": "Validate Python syntax for calculator module"
            },
            {
                "type": "python", 
                "file": "tests/test_calculator.py",
                "description": "Validate Python syntax for test module"
            }
        ]
    }


def mock_llm_response_react_app():
    """Mock LLM response for React app project"""
    return {
        "files": [
            {
                "path": "package.json",
                "content": '''{
  "name": "arxiv-papers-app",
  "version": "1.0.0",
  "description": "React app to browse ArXiv papers",
  "main": "index.js",
  "scripts": {
    "start": "react-scripts start",
    "build": "react-scripts build",
    "test": "react-scripts test",
    "eject": "react-scripts eject"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-scripts": "5.0.1",
    "axios": "^1.4.0"
  },
  "browserslist": {
    "production": [
      ">0.2%",
      "not dead",
      "not op_mini all"
    ],
    "development": [
      "last 1 chrome version",
      "last 1 firefox version",
      "last 1 safari version"
    ]
  }
}''',
                "language": "json",
                "description": "Package.json with React and axios dependencies"
            },
            {
                "path": "src/App.js",
                "content": '''import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [papers, setPapers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('cs.AI');
  const [error, setError] = useState(null);

  const fetchPapers = async (query = 'cs.AI') => {
    setLoading(true);
    setError(null);
    
    try {
      const apiUrl = `https://export.arxiv.org/api/query?search_query=all:${encodeURIComponent(query)}&start=0&max_results=10`;
      const response = await axios.get(apiUrl);
      
      // Parse XML response (simplified - in real app would use proper XML parser)
      const parser = new DOMParser();
      const xmlDoc = parser.parseFromString(response.data, "text/xml");
      const entries = xmlDoc.getElementsByTagName("entry");
      
      const parsedPapers = Array.from(entries).map(entry => ({
        id: entry.querySelector("id")?.textContent || "",
        title: entry.querySelector("title")?.textContent || "No title",
        summary: entry.querySelector("summary")?.textContent || "No abstract",
        authors: Array.from(entry.querySelectorAll("author name")).map(
          author => author.textContent
        ),
        published: entry.querySelector("published")?.textContent || "",
        link: entry.querySelector("id")?.textContent || ""
      }));
      
      setPapers(parsedPapers);
    } catch (err) {
      setError('Failed to fetch papers. Please check your connection.');
      console.error('Error fetching papers:', err);
    }
    
    setLoading(false);
  };

  useEffect(() => {
    fetchPapers();
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchPapers(searchQuery);
  };

  const formatDate = (dateString) => {
    try {
      return new Date(dateString).toLocaleDateString();
    } catch {
      return dateString;
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>ArXiv CS.AI Papers</h1>
        
        <form onSubmit={handleSearch} className="search-form">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search papers (e.g., machine learning, neural networks)"
            className="search-input"
          />
          <button type="submit" disabled={loading} className="search-button">
            {loading ? 'Searching...' : 'Search'}
          </button>
        </form>
      </header>

      <main className="papers-container">
        {error && <div className="error-message">{error}</div>}
        
        {loading && <div className="loading">Loading papers...</div>}
        
        {!loading && papers.length === 0 && !error && (
          <div className="no-papers">No papers found. Try a different search.</div>
        )}
        
        <div className="papers-grid">
          {papers.map((paper, index) => (
            <article key={index} className="paper-card">
              <h2 className="paper-title">
                <a href={paper.link} target="_blank" rel="noopener noreferrer">
                  {paper.title}
                </a>
              </h2>
              
              <div className="paper-authors">
                <strong>Authors:</strong> {paper.authors.join(', ') || 'Unknown'}
              </div>
              
              <div className="paper-date">
                <strong>Published:</strong> {formatDate(paper.published)}
              </div>
              
              <div className="paper-abstract">
                <strong>Abstract:</strong>
                <p>{paper.summary}</p>
              </div>
            </article>
          ))}
        </div>
      </main>
    </div>
  );
}

export default App;
''',
                "language": "javascript",
                "description": "Main React component for browsing ArXiv papers"
            },
            {
                "path": "src/App.css",
                "content": '''.App {
  text-align: center;
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
    'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
    sans-serif;
}

.App-header {
  background-color: #282c34;
  padding: 20px;
  color: white;
  margin-bottom: 20px;
  border-radius: 8px;
}

.App-header h1 {
  margin: 0 0 20px 0;
  font-size: 2.5rem;
}

.search-form {
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
}

.search-input {
  padding: 10px;
  font-size: 16px;
  border: 1px solid #ddd;
  border-radius: 4px;
  min-width: 300px;
  flex: 1;
  max-width: 500px;
}

.search-button {
  padding: 10px 20px;
  font-size: 16px;
  background-color: #61dafb;
  color: #282c34;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}

.search-button:hover:not(:disabled) {
  background-color: #21b7d4;
}

.search-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.papers-container {
  margin-top: 20px;
}

.error-message {
  background-color: #ffebee;
  color: #c62828;
  padding: 16px;
  border-radius: 4px;
  margin: 20px 0;
  border-left: 4px solid #c62828;
}

.loading {
  font-size: 18px;
  color: #666;
  margin: 40px 0;
}

.no-papers {
  font-size: 18px;
  color: #666;
  margin: 40px 0;
}

.papers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 20px;
  margin-top: 20px;
}

.paper-card {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 20px;
  text-align: left;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  transition: transform 0.2s, box-shadow 0.2s;
}

.paper-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

.paper-title {
  margin: 0 0 15px 0;
  font-size: 1.2rem;
  line-height: 1.4;
}

.paper-title a {
  color: #1976d2;
  text-decoration: none;
}

.paper-title a:hover {
  text-decoration: underline;
}

.paper-authors, .paper-date {
  margin: 10px 0;
  font-size: 0.9rem;
  color: #555;
}

.paper-abstract {
  margin-top: 15px;
}

.paper-abstract p {
  margin: 8px 0 0 0;
  line-height: 1.5;
  color: #333;
  font-size: 0.9rem;
}

@media (max-width: 768px) {
  .App {
    padding: 10px;
  }
  
  .App-header h1 {
    font-size: 2rem;
  }
  
  .search-input {
    min-width: 250px;
  }
  
  .papers-grid {
    grid-template-columns: 1fr;
  }
  
  .paper-card {
    padding: 15px;
  }
}
''',
                "language": "css",
                "description": "Styling for the React ArXiv papers app"
            },
            {
                "path": "public/index.html",
                "content": '''<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <link rel="icon" href="%PUBLIC_URL%/favicon.ico" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#000000" />
    <meta
      name="description"
      content="Browse and search ArXiv papers in Computer Science AI"
    />
    <title>ArXiv CS.AI Papers Browser</title>
  </head>
  <body>
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
  </body>
</html>
''',
                "language": "html",
                "description": "HTML template for React app"
            }
        ],
        "scripts": [
            {
                "language": "bash",
                "code": '''#!/bin/bash
echo "Setting up React ArXiv Papers App..."

# Create React project structure
mkdir -p src public

# Create index.js for React
cat > src/index.js << 'EOF'
import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
EOF

# Create basic index.css
cat > src/index.css << 'EOF'
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
    'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background-color: #f5f5f5;
}

code {
  font-family: source-code-pro, Menlo, Monaco, Consolas, 'Courier New',
    monospace;
}

* {
  box-sizing: border-box;
}
EOF

echo "React project structure created!"
echo "Files created:"
echo "  - package.json (dependencies)"
echo "  - src/App.js (main component)"
echo "  - src/App.css (styling)"
echo "  - src/index.js (React entry point)"
echo "  - src/index.css (global styles)"
echo "  - public/index.html (HTML template)"
echo ""
echo "To run the app:"
echo "  1. npm install"
echo "  2. npm start"
''',
                "description": "Setup script for React project structure"
            }
        ],
        "tests": [
            {
                "type": "javascript",
                "file": "src/App.js",
                "description": "Validate JavaScript syntax for React component"
            }
        ]
    }


def demo_task_execution(project_name: str, task_title: str, mock_response_func):
    """Demonstrate task execution with mocked LLM response"""
    print(f"\n{'='*60}")
    print(f"🚀 Demo: {project_name}")
    print(f"{'='*60}")
    
    # Create agent
    agent = create_demo_agent(project_name.lower().replace(" ", "_"))
    
    # Prepare task message
    task_id = "T1"
    plan_state = {
        "tasks_md": [f"# Task {task_id} — {task_title}\nComplete implementation with all necessary files and setup."]
    }
    
    message = Message(data={
        "executor_payload": {
            "task_id": task_id,
            "plan_state": plan_state
        }
    })
    
    # Mock the LLM response
    mock_response = mock_response_func()
    
    with patch.object(agent, '_generate_execution_plan', return_value=mock_response):
        # Execute the task
        print(f"📝 Task: {task_title}")
        print("🔄 Executing task...")
        
        result = agent.run(message)
        
        if result.success:
            print(f"✅ {result.display_output}")
            
            # Show execution details
            if result.output.get("execution_results"):
                print("\n🔨 Execution Details:")
                for exec_result in result.output["execution_results"]:
                    action = exec_result.get("action", "unknown")
                    success = exec_result.get("success", False) 
                    message = exec_result.get("message", "")
                    status = "✅" if success else "❌"
                    print(f"  {status} {action}: {message}")
            
            # Show created files
            project_dir = agent.project_root / task_id
            if project_dir.exists():
                print(f"\n📁 Files created in {project_dir}:")
                for file_path in sorted(project_dir.rglob("*")):
                    if file_path.is_file():
                        rel_path = file_path.relative_to(project_dir)
                        size = file_path.stat().st_size
                        print(f"  📄 {rel_path} ({size} bytes)")
        else:
            print(f"❌ Task failed: {result.output.get('error', 'Unknown error')}")


def main():
    """Run the demo"""
    print("🚀 CodeExecutorAgent Demo")
    print("=" * 80)
    print("This demo shows the CodeExecutorAgent creating real files and executing code")
    print("without requiring an Ollama connection (uses mocked LLM responses).")
    print()
    
    # Demo 1: Python Calculator
    demo_task_execution(
        "Python Calculator",
        "Create Python Calculator with Tests",
        mock_llm_response_python_calculator
    )
    
    # Demo 2: React App  
    demo_task_execution(
        "React ArXiv App", 
        "Create React ArXiv Papers Browser",
        mock_llm_response_react_app
    )
    
    print(f"\n{'='*60}")
    print("✅ Demo completed!")
    print(f"{'='*60}")
    print("Check the ./demo_output/ directory to see the generated files.")
    print("Each project has been created with:")
    print("  - Working source code")
    print("  - Documentation")
    print("  - Setup scripts")
    print("  - Test files")


if __name__ == "__main__":
    main()