import React, { useState, useEffect } from 'react';
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
