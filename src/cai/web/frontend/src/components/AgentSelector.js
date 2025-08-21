import React, { useState, useEffect } from 'react';
import { useApi } from '../contexts/ApiContext';
import './AgentSelector.css';

function AgentSelector({ onSessionCreate }) {
  const api = useApi();
  const [agents, setAgents] = useState([]);
  const [models, setModels] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState('');
  const [selectedModel, setSelectedModel] = useState('');

  useEffect(() => {
    let mounted = true;
    
    const fetchAgentsAndModels = async () => {
      try {
        const [agentsData, modelsData] = await Promise.all([
          api.getAgents(),
          api.getModels(),
        ]);
        
        if (!mounted) return; // Component unmounted, don't update state
        
        setAgents(agentsData);
        setModels(modelsData.models);
        if (agentsData.length > 0) setSelectedAgent(agentsData[0].name);
        // Use current model from backend or first available model
        if (modelsData.current) {
          setSelectedModel(modelsData.current);
        } else if (modelsData.models.length > 0) {
          setSelectedModel(modelsData.models[0].id);
        }
      } catch (error) {
        if (mounted) {
          console.error('Error fetching agents and models:', error);
        }
      }
    };
    
    fetchAgentsAndModels();
    
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Remove api dependency to prevent continuous calls

  const createSession = async () => {
    try {
      const sessionData = {
        name: `Session ${new Date().toLocaleTimeString()}`,
        agent_type: selectedAgent,
        model: selectedModel,
      };
      const session = await api.createSession(sessionData);
      onSessionCreate(session);
    } catch (error) {
      console.error('Error creating session:', error);
    }
  };

  return (
    <div className="agent-selector">
      <h3>Select Agent</h3>
      <select value={selectedAgent} onChange={(e) => setSelectedAgent(e.target.value)}>
        {agents.map((agent) => (
          <option key={agent.name} value={agent.name}>
            {agent.display_name}
          </option>
        ))}
      </select>

      <h3>Select Model</h3>
      <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
        {models.map((model) => (
          <option key={model.id} value={model.id}>
            {model.name}
          </option>
        ))}
      </select>

      <button onClick={createSession} disabled={!selectedAgent || !selectedModel}>
        Create Session
      </button>
    </div>
  );
}

export default AgentSelector;

