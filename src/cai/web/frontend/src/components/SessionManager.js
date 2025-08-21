import React, { useEffect } from 'react';
import { useApi } from '../contexts/ApiContext';
import { useWebSocket } from '../contexts/WebSocketContext';
import './SessionManager.css';

function SessionManager({ sessions, setSessions, selectedSession, setSelectedSession }) {
  const api = useApi();
  const { connect, disconnect } = useWebSocket();

  useEffect(() => {
    let mounted = true;
    
    // Fetch existing sessions on mount
    const fetchSessions = async () => {
      try {
        const sessionsData = await api.getSessions();
        if (mounted) {
          setSessions(sessionsData);
        }
      } catch (error) {
        if (mounted) {
          console.error('Error fetching sessions:', error);
        }
      }
    };
    
    fetchSessions();
    
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Remove dependencies to prevent continuous calls

  useEffect(() => {
    // Connect WebSocket when session is selected
    if (selectedSession) {
      connect(selectedSession.id);
    } else {
      disconnect();
    }
  }, [selectedSession, connect, disconnect]);

  const deleteSession = async (sessionId) => {
    try {
      await api.deleteSession(sessionId);
      setSessions(sessions.filter(s => s.id !== sessionId));
      if (selectedSession?.id === sessionId) {
        setSelectedSession(null);
      }
    } catch (error) {
      console.error('Error deleting session:', error);
    }
  };

  return (
    <div className="session-manager">
      <h3>Sessions</h3>
      <div className="session-list">
        {sessions.length === 0 ? (
          <p className="no-sessions">No active sessions</p>
        ) : (
          sessions.map((session) => (
            <div
              key={session.id}
              className={`session-item ${selectedSession?.id === session.id ? 'selected' : ''}`}
              onClick={() => setSelectedSession(session)}
            >
              <div className="session-info">
                <div className="session-name">{session.name}</div>
                <div className="session-details">
                  <span className="agent-type">{session.agent_type}</span>
                  <span className="model">{session.model}</span>
                </div>
              </div>
              <button
                className="delete-btn danger"
                onClick={(e) => {
                  e.stopPropagation();
                  deleteSession(session.id);
                }}
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default SessionManager;
