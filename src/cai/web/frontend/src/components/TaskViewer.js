import React, { useState, useEffect } from 'react';
import { useApi } from '../contexts/ApiContext';
import { useWebSocket } from '../contexts/WebSocketContext';
import './TaskViewer.css';

function TaskViewer({ sessionId }) {
  const api = useApi();
  const { addListener } = useWebSocket();
  const [tasks, setTasks] = useState([]);
  const [expandedTasks, setExpandedTasks] = useState(new Set());

  useEffect(() => {
    let mounted = true;
    
    // Fetch initial tasks
    const fetchTasks = async () => {
      try {
        const tasksData = await api.getSessionTasks(sessionId);
        if (mounted) {
          setTasks(tasksData);
        }
      } catch (error) {
        if (mounted) {
          console.error('Error fetching tasks:', error);
        }
      }
    };
    
    fetchTasks();

    // Listen for task updates
    const removeTaskUpdateListener = addListener('task_update', (data) => {
      if (mounted) {
        setTasks(prevTasks => {
          const index = prevTasks.findIndex(t => t.id === data.task.id);
          if (index >= 0) {
            const newTasks = [...prevTasks];
            newTasks[index] = data.task;
            return newTasks;
          }
          return prevTasks;
        });
      }
    });

    const removeTaskCreatedListener = addListener('task_created', (data) => {
      if (mounted) {
        setTasks(prevTasks => [...prevTasks, data.task]);
      }
    });

    return () => {
      mounted = false;
      removeTaskUpdateListener();
      removeTaskCreatedListener();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]); // Remove api and addListener dependencies

  const toggleTaskExpanded = (taskId) => {
    setExpandedTasks(prev => {
      const newSet = new Set(prev);
      if (newSet.has(taskId)) {
        newSet.delete(taskId);
      } else {
        newSet.add(taskId);
      }
      return newSet;
    });
  };

  const cancelTask = async (taskId) => {
    try {
      await api.cancelTask(taskId);
    } catch (error) {
      console.error('Error cancelling task:', error);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'pending':
        return '⏳';
      case 'running':
        return '🔄';
      case 'completed':
        return '✅';
      case 'failed':
        return '❌';
      case 'cancelled':
        return '🚫';
      default:
        return '❓';
    }
  };

  return (
    <div className="task-viewer">
      <h3>Tasks</h3>
      <div className="task-list">
        {tasks.length === 0 ? (
          <p className="no-tasks">No tasks yet</p>
        ) : (
          tasks.map((task) => (
            <div key={task.id} className={`task-item ${task.status}`}>
              <div className="task-header" onClick={() => toggleTaskExpanded(task.id)}>
                <span className="status-icon">{getStatusIcon(task.status)}</span>
                <div className="task-info">
                  <div className="task-message">{task.message}</div>
                  <div className="task-meta">
                    <span className="task-status">{task.status}</span>
                    {task.duration && (
                      <span className="task-duration">{task.duration.toFixed(2)}s</span>
                    )}
                    {task.tools_used.length > 0 && (
                      <span className="task-tools">🔧 {task.tools_used.join(', ')}</span>
                    )}
                  </div>
                </div>
                {task.status === 'running' && (
                  <button
                    className="cancel-btn danger"
                    onClick={(e) => {
                      e.stopPropagation();
                      cancelTask(task.id);
                    }}
                  >
                    Cancel
                  </button>
                )}
              </div>
              
              {expandedTasks.has(task.id) && (
                <div className="task-details">
                  {task.result && (
                    <div className="task-result">
                      <h4>Result:</h4>
                      <pre>{typeof task.result === 'string' ? task.result : JSON.stringify(task.result, null, 2)}</pre>
                    </div>
                  )}
                  {task.error && (
                    <div className="task-error">
                      <h4>Error:</h4>
                      <pre>{task.error}</pre>
                    </div>
                  )}
                  {task.metadata && task.metadata.initial_thinking && (
                    <div className="task-thinking">
                      <h4>Initial Thinking:</h4>
                      <div className="thinking-content">{task.metadata.initial_thinking}</div>
                    </div>
                  )}
                  {task.metadata && task.metadata.tool_outputs && Object.keys(task.metadata.tool_outputs).length > 0 && (
                    <div className="tool-outputs">
                      <h4>Tool Outputs:</h4>
                      {Object.entries(task.metadata.tool_outputs).map(([index, output]) => (
                        <div key={index} className="tool-output">
                          <pre className="output-content">{output}</pre>
                        </div>
                      ))}
                    </div>
                  )}
                  {task.logs && task.logs.length > 0 && (
                    <div className="task-logs">
                      <h4>Logs:</h4>
                      {task.logs.map((log, index) => (
                        <div key={index} className="log-entry">
                          <span className="log-time">{new Date(log.timestamp).toLocaleTimeString()}</span>
                          <span className="log-type">{log.type}</span>
                          {log.tool && <span className="log-tool">{log.tool}</span>}
                          <pre className="log-content">{log.result || log.error}</pre>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default TaskViewer;
