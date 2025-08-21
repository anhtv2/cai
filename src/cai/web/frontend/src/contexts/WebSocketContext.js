import React, { createContext, useContext, useEffect, useState, useRef } from 'react';

const WebSocketContext = createContext();

const WS_BASE_URL = process.env.REACT_APP_WS_URL || 'ws://localhost:8000';

export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocket must be used within WebSocketProvider');
  }
  return context;
};

export const WebSocketProvider = ({ children }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const wsRef = useRef(null);
  const listenersRef = useRef(new Map());
  const reconnectTimeoutRef = useRef(null);
  const currentSessionRef = useRef(null);

  const addListener = (event, callback) => {
    if (!listenersRef.current.has(event)) {
      listenersRef.current.set(event, new Set());
    }
    listenersRef.current.get(event).add(callback);

    // Return cleanup function
    return () => {
      const listeners = listenersRef.current.get(event);
      if (listeners) {
        listeners.delete(callback);
        if (listeners.size === 0) {
          listenersRef.current.delete(event);
        }
      }
    };
  };

  const notifyListeners = (event, data) => {
    const listeners = listenersRef.current.get(event);
    if (listeners) {
      listeners.forEach(callback => callback(data));
    }
  };

  const connect = (sessionId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN && currentSessionRef.current === sessionId) {
      return;
    }

    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    currentSessionRef.current = sessionId;
    const ws = new WebSocket(`${WS_BASE_URL}/ws/${sessionId}`);

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
      clearTimeout(reconnectTimeoutRef.current);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLastMessage(data);
        
        // Notify specific listeners based on message type
        if (data.type) {
          notifyListeners(data.type, data);
        }
        
        // Notify general message listeners
        notifyListeners('message', data);
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
      wsRef.current = null;

      // Attempt to reconnect after 3 seconds
      if (currentSessionRef.current) {
        reconnectTimeoutRef.current = setTimeout(() => {
          connect(currentSessionRef.current);
        }, 3000);
      }
    };

    wsRef.current = ws;
  };

  const disconnect = () => {
    clearTimeout(reconnectTimeoutRef.current);
    currentSessionRef.current = null;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  };

  const sendMessage = (data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    } else {
      console.error('WebSocket is not connected');
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const value = {
    isConnected,
    lastMessage,
    connect,
    disconnect,
    sendMessage,
    addListener,
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};
