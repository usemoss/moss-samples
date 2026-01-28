'use client'

import { useState, useTransition } from 'react';
import { searchMoss } from './actions';
import { 
  Search, 
  Zap, 
  Activity, 
  Timer, 
  ArrowRight, 
  AlertCircle, 
  LayoutGrid,
  SearchCheck,
  Ghost
} from 'lucide-react';

export default function MossDemo() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<{ timeTaken: number; count: number } | null>(null);
  const [isPending, startTransition] = useTransition();

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isPending) return;

    setError(null);

    startTransition(async () => {
      try {
        const response = await searchMoss(query);
        if (response.success) {
          setResults(response.docs || []);
          setStats({ 
            timeTaken: response.timeTaken || 0,
            count: response.docs?.length || 0 
          });
        } else {
          setError(response.error || "Search failed");
          setResults([]);
        }
      } catch (err) {
        setError("Network switch or environment configuration error.");
        setResults([]);
      }
    });
  };

  return (
    <main>
      <div className="container">
        <header className="logo-section">
          <div className="logo-badge">Next.js 15 + Moss SDK demo</div>
          <h1 className="title">Moss Intelligence</h1>
          <p style={{ color: '#94a3b8', fontSize: '1.2rem', maxWidth: '600px', margin: '0 auto' }}>
            Experience sub-10ms semantic retrieval with industry-grade precision.
          </p>
        </header>

        <div className="glass-card">
          <form onSubmit={handleSearch} className="search-container">
            <div className="search-input-group">
              <div className="search-icon">
                <Search size={22} strokeWidth={2.5} />
              </div>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask anything from your knowledge base..."
                autoFocus
              />
              <button 
                className="search-button" 
                type="submit" 
                disabled={isPending || !query.trim()}
              >
                {isPending ? (
                  <>Processing...</>
                ) : (
                  <>
                    Search <ArrowRight size={18} />
                  </>
                )}
              </button>
            </div>
          </form>

          {error && (
            <div className="error-box">
              <AlertCircle size={20} />
              <div>
                <strong>Configuration Error:</strong> {error}
              </div>
            </div>
          )}

          {stats && !isPending && (
            <div className="stats">
              <div className="stat-item">
                <SearchCheck size={16} />
                <span>{stats.count} Matches</span>
              </div>
            </div>
          )}

          <div className="results-list">
            {results.map((doc, idx) => (
              <div 
                key={doc.id} 
                className="result-card" 
                style={{ animationDelay: `${idx * 0.08}s` }}
              >
                <div className="result-header">
                  <div className={`match-score ${doc.score > 0.8 ? 'high' : 'mid'}`}>
                    <Zap size={14} fill="currentColor" />
                    {(doc.score * 100).toFixed(1)}% Relevance
                  </div>
                  <div style={{ color: '#475569', fontSize: '0.7rem' }}>ID: {doc.id}</div>
                </div>
                <div className="result-text">{doc.text}</div>
                {doc.metadata && (
                  <div className="metadata-pills">
                    {Object.entries(doc.metadata).map(([key, value]) => (
                      <span key={key} className="pill">
                        {key.toUpperCase()}: {String(value)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {results.length === 0 && !isPending && !error && (
              <div className="empty-state">
                {query ? (
                  <>
                    <Ghost size={48} strokeWidth={1} style={{ marginBottom: '1rem', opacity: 0.3 }} />
                    <p>No semantic matches found for your query.</p>
                  </>
                ) : (
                  <>
                    <LayoutGrid size={48} strokeWidth={1} style={{ marginBottom: '1rem', opacity: 0.2 }} />
                    <p>Type a query above to explore your vector index.</p>
                  </>
                )}
              </div>
            )}

            {isPending && (
              <div className="empty-state">
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
                  <div className="logo-badge" style={{ animation: 'pulse 1.5s infinite speed' }}>
                    Querying...
                  </div>
                  <style jsx>{`
                    @keyframes pulse {
                      0% { opacity: 0.5; }
                      50% { opacity: 1; }
                      100% { opacity: 0.5; }
                    }
                  `}</style>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <footer>
        Powering tomorrow's reach with Moss
      </footer>
    </main>
  );
}
