import React, { useState, useEffect } from 'react';
import { useApi } from '../contexts/ApiContext';
import { useWebSocket } from '../contexts/WebSocketContext';
import './SessionChat.css';

function SessionChat({ session }) {
  const api = useApi();
  const { addListener } = useWebSocket();
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    let mounted = true;
    
    // Load existing messages when session changes
    const loadMessages = async () => {
      try {
        const response = await api.getSessionMessages(session.id);
        if (mounted) {
          setMessages(response.messages);
        }
      } catch (error) {
        if (mounted) {
          console.error('Error loading messages:', error);
        }
      }
    };
    
    loadMessages();

    // Listen for new messages
    const removeMessageListener = addListener('message_added', (data) => {
      if (mounted) {
        setMessages(prev => [...prev, data.message]);
      }
    });

    return () => {
      mounted = false;
      removeMessageListener();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id]); // Remove api and addListener dependencies

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!message.trim() || sending) return;

    setSending(true);
    
    // Add user message immediately to UI
    const userMsg = {
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
      tools_used: [],
      task_id: null
    };
    setMessages(prev => [...prev, userMsg]);
    
    try {
      const response = await api.sendMessage(session.id, message);
      // Update the user message and add assistant response
      setMessages(prev => [
        ...prev.slice(0, -1), // Remove temporary user message
        userMsg, // Add proper user message
        response.message // Add assistant response
      ]);
      setMessage('');
    } catch (error) {
      console.error('Error sending message:', error);
      alert('Failed to send message: ' + error.message);
      // Remove the temporary user message on error
      setMessages(prev => prev.slice(0, -1));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="session-chat">
      <div className="session-header">
        <h2>{session.name}</h2>
        <div className="session-info">
          <span className="agent-badge">{session.agent_type}</span>
          <span className="model-badge">{session.model}</span>
          <span className="status-badge">{session.status}</span>
        </div>
      </div>
      
      <div className="chat-messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`message ${msg.role} ${msg.is_thinking ? 'thinking' : ''}`}>
            <div className="message-header">
              <span className="message-role">
                {msg.role === 'user' ? 'You' : session.agent_type}
                {msg.is_thinking && ' >>'}
              </span>
              <span className="message-time">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </span>
              {msg.is_thinking && (
                <span className="thinking-indicator">💭 thinking</span>
              )}
              {msg.tools_used && msg.tools_used.length > 0 && (
                <span className="tools-indicator">🔧 {msg.tools_used.length} tools used</span>
              )}
            </div>
            <div className="message-content">
              {msg.content}
            </div>
            {msg.task_id && (
              <div className="task-link">
                <button 
                  className="view-task-btn"
                  onClick={() => {
                    // This will be handled by parent component or router
                    console.log('View task:', msg.task_id);
                  }}
                >
                  View Task Details →
                </button>
              </div>
            )}
          </div>
        ))}
        {sending && (
          <div className="message assistant typing">
            <div className="message-header">
              <span className="message-role">{session.agent_type}</span>
              <span className="message-time">thinking...</span>
            </div>
            <div className="message-content">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
      </div>
      
      <form className="message-form" onSubmit={sendMessage}>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Enter your message for the agent..."
          rows="3"
          disabled={sending}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              sendMessage(e);
            }
          }}
        />
        <button type="submit" disabled={!message.trim() || sending}>
          {sending ? 'Sending...' : 'Send Message'}
        </button>
      </form>
    </div>
  );
}

export default SessionChat;
