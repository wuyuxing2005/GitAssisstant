import { useState, useEffect } from "react";
import { labelStatus } from "../utils/labels";

interface TaskProgressProps {
  taskId: string;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

interface TaskProgressState {
  taskId: string;
  status: string;
  isProcessing: boolean;
  message: string;
}

export function TaskProgress({ taskId, onComplete, onError }: TaskProgressProps) {
  const [progress, setProgress] = useState<TaskProgressState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchProgress = async () => {
      try {
        const response = await fetch(`http://localhost:8000/api/tasks/${taskId}/progress`);
        if (!response.ok) {
          throw new Error(`获取任务进度失败：${response.status}`);
        }
        const data = await response.json();
        setProgress(data);

        if (data.status === "completed") {
          setLoading(false);
          onComplete?.();
        } else if (data.status === "failed") {
          setLoading(false);
          onError?.("任务执行失败");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "未知错误");
        setLoading(false);
        onError?.(err instanceof Error ? err.message : "未知错误");
      }
    };

    // 立即获取一次进度
    fetchProgress();

    // 轮询进度（每 2 秒一次）
    const intervalId = setInterval(fetchProgress, 2000);

    return () => clearInterval(intervalId);
  }, [taskId, onComplete, onError]);

  if (loading && !progress) {
    return (
      <div className="task-progress loading">
        <div className="progress-spinner"></div>
        <span>任务状态加载中...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="task-progress error">
        <span className="error-icon">!</span>
        <span>{error}</span>
      </div>
    );
  }

  if (!progress) {
    return null;
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return "✓";
      case "failed":
        return "✗";
      case "running":
        return "⟳";
      default:
        return "○";
    }
  };

  const getStatusClass = (status: string) => {
    switch (status) {
      case "completed":
        return "status-completed";
      case "failed":
        return "status-failed";
      case "running":
        return "status-running";
      default:
        return "status-pending";
    }
  };

  return (
    <div className={`task-progress ${getStatusClass(progress.status)}`}>
      <div className="progress-header">
        <span className="status-icon">{getStatusIcon(progress.status)}</span>
        <span className="status-text">{labelStatus(progress.status)}</span>
      </div>
      <div className="progress-body">
        {progress.isProcessing ? (
          <div className="processing-indicator">
            <div className="spinner"></div>
            <span>处理中...</span>
          </div>
        ) : (
          <span>{progress.message}</span>
        )}
      </div>
      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{
            width: progress.status === "completed" ? "100%" : progress.status === "failed" ? "0%" : "50%",
          }}
        />
      </div>
    </div>
  );
}
