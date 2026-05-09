import { useState } from "react";
import type { AgentTrace } from "../types/trace";
import { labelTraceEvent } from "../utils/labels";

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
        throw new Error(`加载执行链路失败：${response.status}`);
      }
      const data = await response.json();
      setTraces(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "未知错误");
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
    return <div className="trace-viewer loading">执行链路加载中...</div>;
  }

  if (error) {
    return (
      <div className="trace-viewer error">
        <p>{error}</p>
        <button onClick={loadTraces}>重试</button>
      </div>
    );
  }

  if (!traces || traces.length === 0) {
    return (
      <div className="trace-viewer empty">
        <p>当前任务暂无执行链路数据。</p>
        <button onClick={loadTraces}>加载执行链路</button>
      </div>
    );
  }

  return (
    <div className="trace-viewer">
      <div className="trace-header">
        <h3>执行链路（{traces.length}）</h3>
        <button onClick={loadTraces} className="btn-secondary">
          刷新
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
              <span className="trace-events-count">{trace.events.length} 个事件</span>
            </div>
            <div className="trace-item-body">
              <span className="trace-input">{trace.user_input}</span>
              <span className="trace-response">{trace.final_response}</span>
            </div>
            <div className="trace-item-meta">
              <span>延迟：{(trace.total_latency_ms / 1000).toFixed(2)}s</span>
              <span>Token：{trace.token_usage.total}</span>
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
          <h4>执行链路详情：{trace.sample_id}</h4>
          <button onClick={onClose} className="btn-close">
            ×
          </button>
        </div>

        <div className="trace-detail-body">
          <div className="trace-summary">
            <div className="trace-field">
              <strong>用户输入：</strong>
              <p>{trace.user_input}</p>
            </div>
            <div className="trace-field">
              <strong>最终回答：</strong>
              <p>{trace.final_response}</p>
            </div>
            <div className="trace-stats">
              <div className="stat-item">
                <span>总延迟：</span>
                <strong>{(trace.total_latency_ms / 1000).toFixed(2)}s</strong>
              </div>
              <div className="stat-item">
                <span>提示词 Token：</span>
                <strong>{trace.token_usage.prompt}</strong>
              </div>
              <div className="stat-item">
                <span>生成 Token：</span>
                <strong>{trace.token_usage.completion}</strong>
              </div>
              <div className="stat-item">
                <span>总 Token：</span>
                <strong>{trace.token_usage.total}</strong>
              </div>
            </div>
          </div>

          <div className="trace-events">
            <h5>事件时间线（{trace.events.length} 个事件）</h5>
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
                    <span className="event-type">{labelTraceEvent(event.event_type)}</span>
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
                          <strong>消息：</strong>
                          <p>{event.message}</p>
                        </div>
                      )}

                      {event.tool_call && (
                        <div className="event-field">
                          <strong>工具调用：</strong>
                          <div className="tool-call-detail">
                            <div className="tool-name">
                              <strong>名称：</strong> {event.tool_call.name}
                            </div>
                            <div className="tool-status">
                              <strong>状态：</strong>{" "}
                              <span
                                className={`status-badge ${event.tool_call.status}`}
                              >
                                {event.tool_call.status}
                              </span>
                            </div>
                            <div className="tool-latency">
                              <strong>耗时：</strong>{" "}
                              {event.tool_call.latency_ms}ms
                            </div>
                            {event.tool_call.arguments &&
                              Object.keys(event.tool_call.arguments).length > 0 && (
                                <div className="tool-arguments">
                                  <strong>参数：</strong>
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
                                <strong>结果：</strong>
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
                          <strong>元数据：</strong>
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
