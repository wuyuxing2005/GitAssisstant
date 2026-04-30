import { useState } from "react";
import type { AgentTrace } from "../types/trace";

interface TraceViewerProps {
  taskId: string;
  traces?: AgentTrace[];
}

export function TraceViewer({ taskId, traces: initialTraces }: TraceViewerProps) {
  const [traces, setTraces] = useState<AgentTrace[] | undefined>(initialTraces);
  const [selectedTrace, setSelectedTrace] = useState<AgentTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTraces = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`http://localhost:8000/api/traces/${taskId}`);
      if (!response.ok) {
        if (response.status === 404) {
          setTraces([]);
          return;
        }
        throw new Error(`Failed to load traces: ${response.status}`);
      }
      const data = await response.json();
      setTraces(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleTraceSelect = (trace: AgentTrace) => {
    setSelectedTrace(trace);
  };

  const handleCloseDetail = () => {
    setSelectedTrace(null);
  };

  if (loading) {
    return <div className="trace-viewer loading">Loading traces...</div>;
  }

  if (error) {
    return (
      <div className="trace-viewer error">
        <p>{error}</p>
        <button onClick={loadTraces}>Retry</button>
      </div>
    );
  }

  if (!traces || traces.length === 0) {
    return (
      <div className="trace-viewer empty">
        <p>No trace data available for this task.</p>
        <button onClick={loadTraces}>Load Traces</button>
      </div>
    );
  }

  return (
    <div className="trace-viewer">
      <div className="trace-header">
        <h3>Execution Traces ({traces.length})</h3>
        <button onClick={loadTraces} className="btn-secondary">
          Refresh
        </button>
      </div>

      <div className="trace-list">
        {traces.map((trace) => (
          <div
            key={trace.trace_id}
            className={`trace-item ${selectedTrace?.trace_id === trace.trace_id ? "selected" : ""}`}
            onClick={() => handleTraceSelect(trace)}
          >
            <div className="trace-item-header">
              <span className="trace-sample-id">{trace.sample_id}</span>
              <span className="trace-events-count">{trace.events.length} events</span>
            </div>
            <div className="trace-item-body">
              <span className="trace-input">{trace.user_input}</span>
              <span className="trace-response">{trace.final_response}</span>
            </div>
            <div className="trace-item-meta">
              <span>Latency: {(trace.total_latency_ms / 1000).toFixed(2)}s</span>
              <span>Tokens: {trace.token_usage.total}</span>
            </div>
          </div>
        ))}
      </div>

      {selectedTrace && (
        <TraceDetail trace={selectedTrace} onClose={handleCloseDetail} />
      )}
    </div>
  );
}

interface TraceDetailProps {
  trace: AgentTrace;
  onClose: () => void;
}

function TraceDetail({ trace, onClose }: TraceDetailProps) {
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());

  const toggleEvent = (eventId: string) => {
    setExpandedEvents((prev) => {
      const next = new Set(prev);
      if (next.has(eventId)) {
        next.delete(eventId);
      } else {
        next.add(eventId);
      }
      return next;
    });
  };

  const getEventTypeIcon = (eventType: string) => {
    const icons: Record<string, string> = {
      tool_call: "🔧",
      tool_result: "📤",
      llm_generation: "🤖",
      user_input: "👤",
      system_message: "ℹ️",
      error: "❌",
    };
    return icons[eventType] || "📝";
  };

  const getEventTypeColor = (eventType: string) => {
    const colors: Record<string, string> = {
      tool_call: "#3b82f6",
      tool_result: "#10b981",
      llm_generation: "#8b5cf6",
      user_input: "#6b7280",
      system_message: "#6b7280",
      error: "#ef4444",
    };
    return colors[eventType] || "#6b7280";
  };

  return (
    <div className="trace-detail-overlay" onClick={onClose}>
      <div className="trace-detail" onClick={(e) => e.stopPropagation()}>
        <div className="trace-detail-header">
          <h4>Trace Details: {trace.sample_id}</h4>
          <button onClick={onClose} className="btn-close">
            ×
          </button>
        </div>

        <div className="trace-detail-body">
          <div className="trace-summary">
            <div className="trace-field">
              <strong>User Input:</strong>
              <p>{trace.user_input}</p>
            </div>
            <div className="trace-field">
              <strong>Final Response:</strong>
              <p>{trace.final_response}</p>
            </div>
            <div className="trace-stats">
              <div className="stat-item">
                <span>Total Latency:</span>
                <strong>{(trace.total_latency_ms / 1000).toFixed(2)}s</strong>
              </div>
              <div className="stat-item">
                <span>Prompt Tokens:</span>
                <strong>{trace.token_usage.prompt}</strong>
              </div>
              <div className="stat-item">
                <span>Completion Tokens:</span>
                <strong>{trace.token_usage.completion}</strong>
              </div>
              <div className="stat-item">
                <span>Total Tokens:</span>
                <strong>{trace.token_usage.total}</strong>
              </div>
            </div>
          </div>

          <div className="trace-events">
            <h5>Event Timeline ({trace.events.length} events)</h5>
            <div className="event-list">
              {trace.events.map((event, index) => (
                <div
                  key={event.id}
                  className={`event-item ${expandedEvents.has(event.id) ? "expanded" : ""}`}
                >
                  <div
                    className="event-header"
                    onClick={() => toggleEvent(event.id)}
                  >
                    <span
                      className="event-icon"
                      style={{ borderColor: getEventTypeColor(event.event_type) }}
                    >
                      {getEventTypeIcon(event.event_type)}
                    </span>
                    <span className="event-type">{event.event_type}</span>
                    <span className="event-index">#{index + 1}</span>
                    <span className="event-time">
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </span>
                    <span className="event-expand">{expandedEvents.has(event.id) ? "▼" : "▶"}</span>
                  </div>

                  {expandedEvents.has(event.id) && (
                    <div className="event-details">
                      {event.message && (
                        <div className="event-field">
                          <strong>Message:</strong>
                          <p>{event.message}</p>
                        </div>
                      )}

                      {event.tool_call && (
                        <div className="event-field">
                          <strong>Tool Call:</strong>
                          <div className="tool-call-detail">
                            <div className="tool-name">
                              <strong>Name:</strong> {event.tool_call.name}
                            </div>
                            <div className="tool-status">
                              <strong>Status:</strong>{" "}
                              <span
                                className={`status-badge ${event.tool_call.status}`}
                              >
                                {event.tool_call.status}
                              </span>
                            </div>
                            <div className="tool-latency">
                              <strong>Latency:</strong>{" "}
                              {event.tool_call.latency_ms}ms
                            </div>
                            {event.tool_call.arguments &&
                              Object.keys(event.tool_call.arguments).length > 0 && (
                                <div className="tool-arguments">
                                  <strong>Arguments:</strong>
                                  <pre>
                                    {JSON.stringify(
                                      event.tool_call.arguments,
                                      null,
                                      2
                                    )}
                                  </pre>
                                </div>
                              )}
                            {event.tool_call.result !== undefined && (
                              <div className="tool-result">
                                <strong>Result:</strong>
                                <pre>
                                  {typeof event.tool_call.result === "string"
                                    ? event.tool_call.result
                                    : JSON.stringify(
                                        event.tool_call.result,
                                        null,
                                        2
                                      )}
                                </pre>
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {event.metadata && Object.keys(event.metadata).length > 0 && (
                        <div className="event-field">
                          <strong>Metadata:</strong>
                          <pre>
                            {JSON.stringify(event.metadata, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
