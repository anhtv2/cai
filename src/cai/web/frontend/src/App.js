import React, { useState } from 'react';
import './App.css';
import SessionManager from './components/SessionManager';
import TaskViewer from './components/TaskViewer';
import AgentSelector from './components/AgentSelector';
import SessionChat from './components/SessionChat';
import { WebSocketProvider } from './contexts/WebSocketContext';
import { ApiProvider } from './contexts/ApiContext';

function App() {
  const [selectedSession, setSelectedSession] = useState(null);
  const [sessions, setSessions] = useState([]);

  return (
    <ApiProvider>
      <WebSocketProvider>
        <div className="App">
          <header className="App-header">
            <h1>CAI Web Interface</h1>
            <p>Cybersecurity AI Framework</p>
          </header>
          
          <div className="container">
            <div className="sidebar">
              <AgentSelector 
                onSessionCreate={(session) => {
                  setSessions([...sessions, session]);
                  setSelectedSession(session);
                }}
              />
              <SessionManager 
                sessions={sessions}
                setSessions={setSessions}
                selectedSession={selectedSession}
                setSelectedSession={setSelectedSession}
              />
            </div>
            
            <div className="main-content">
              {selectedSession ? (
                <>
                  <SessionChat session={selectedSession} />
                  <TaskViewer sessionId={selectedSession.id} />
                </>
              ) : (
                <div className="welcome">
                  <h2>Welcome to CAI Web</h2>
                  <p>Select an agent and create a session to get started</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </WebSocketProvider>
    </ApiProvider>
  );
}

export default App;
