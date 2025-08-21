import React, { createContext, useContext } from 'react';

const ApiContext = createContext();

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export const useApi = () => {
  const context = useContext(ApiContext);
  if (!context) {
    throw new Error('useApi must be used within ApiProvider');
  }
  return context;
};

export const ApiProvider = ({ children }) => {
  const apiCall = React.useCallback(async (endpoint, options = {}) => {
    const url = `${API_BASE_URL}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `API Error: ${response.status}`);
    }

    return response.json();
  }, []);

  const api = React.useMemo(() => ({
    // Session endpoints
    createSession: (data) => apiCall('/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

    getSessions: () => apiCall('/sessions'),

    getSession: (sessionId) => apiCall(`/sessions/${sessionId}`),

    deleteSession: (sessionId) => apiCall(`/sessions/${sessionId}`, {
      method: 'DELETE',
    }),

    // Message/Task endpoints
    sendMessage: (sessionId, message) => apiCall(`/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content: message }),
    }),

    getSessionMessages: (sessionId) => apiCall(`/sessions/${sessionId}/messages`),

    getSessionTasks: (sessionId) => apiCall(`/sessions/${sessionId}/tasks`),

    getTask: (taskId) => apiCall(`/tasks/${taskId}`),

    cancelTask: (taskId) => apiCall(`/tasks/${taskId}/cancel`, {
      method: 'POST',
    }),

    // Agent endpoints
    getAgents: () => apiCall('/agents'),

    getModels: () => apiCall('/models'),
  }), [apiCall]);

  return (
    <ApiContext.Provider value={api}>
      {children}
    </ApiContext.Provider>
  );
};
