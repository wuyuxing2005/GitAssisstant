import { useState, useEffect } from "react";
import { fetchDatasets, deleteDataset, type DatasetInfo } from "../services/api";
import { DatasetUploader } from "../components/DatasetUploader";

interface DatasetsPageProps {
  onDatasetUpdated?: () => void;
}

const formatDate = (timestamp: number) => {
  return new Date(timestamp * 1000).toLocaleDateString();
};

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

export function DatasetsPage({ onDatasetUpdated }: DatasetsPageProps) {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDataset, setSelectedDataset] = useState<DatasetInfo | null>(null);
  const [showUploader, setShowUploader] = useState(false);

  const loadDatasets = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDatasets();
      setDatasets(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载数据集失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDatasets();
  }, []);

  const handleUploadComplete = (result: { message: string; dataset_name: string; line_count: number }) => {
    setShowUploader(false);
    loadDatasets();
    onDatasetUpdated?.();
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`确定删除数据集“${name}”吗？`)) {
      return;
    }

    try {
      await deleteDataset(name);
      loadDatasets();
      onDatasetUpdated?.();
    } catch (err) {
      alert(err instanceof Error ? err.message : "删除数据集失败");
    }
  };

  if (loading) {
    return (
      <section className="card">
        <div className="section-header">
          <h2>数据集</h2>
        </div>
        <div className="loading-state">数据集加载中...</div>
      </section>
    );
  }

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>数据集</h2>
          <p>管理评测任务使用的 JSONL 数据集。</p>
        </div>
        <button
          className="primary-button"
          onClick={() => setShowUploader(!showUploader)}
        >
          {showUploader ? "取消" : "上传数据集"}
        </button>
      </div>

      {showUploader && (
        <div className="uploader-section">
          <DatasetUploader
            onUploadComplete={handleUploadComplete}
            onError={(err) => alert(err)}
          />
        </div>
      )}

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      {datasets.length === 0 ? (
        <div className="empty-state">
          <p>暂无数据集。</p>
          <p>上传 JSONL 文件后即可创建评测任务。</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="task-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>记录数</th>
                <th>大小</th>
                <th>修改时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {datasets.map((dataset) => (
                <tr key={dataset.name}>
                  <td>
                    <strong>{dataset.name}</strong>
                    <br />
                    <small>{dataset.file_name}</small>
                  </td>
                  <td>{dataset.line_count.toLocaleString()}</td>
                  <td>{formatSize(dataset.size_bytes)}</td>
                  <td>{formatDate(dataset.modified_at)}</td>
                  <td>
                    <div className="inline-actions">
                      <button
                        className="ghost-button"
                        onClick={() => setSelectedDataset(dataset)}
                      >
                        查看
                      </button>
                      <button
                        className="ghost-button danger"
                        onClick={() => handleDelete(dataset.name)}
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedDataset && (
        <DatasetDetail
          dataset={selectedDataset}
          onClose={() => setSelectedDataset(null)}
        />
      )}
    </section>
  );
}

interface DatasetDetailProps {
  dataset: DatasetInfo;
  onClose: () => void;
}

function DatasetDetail({ dataset, onClose }: DatasetDetailProps) {
  const [preview, setPreview] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadPreview = async () => {
      try {
        const response = await fetch(`http://localhost:8000/api/datasets/${dataset.name}?limit=10`);
        const data = await response.json();
        setPreview(data.preview || []);
      } catch (err) {
        console.error("加载预览失败:", err);
      } finally {
        setLoading(false);
      }
    };

    loadPreview();
  }, [dataset.name]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>数据集：{dataset.name}</h3>
          <button className="btn-close-circle" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="dataset-stats">
            <div className="stat-item">
              <span>记录数</span>
              <strong>{dataset.line_count.toLocaleString()}</strong>
            </div>
            <div className="stat-item">
              <span>大小</span>
              <strong>{formatSize(dataset.size_bytes)}</strong>
            </div>
            <div className="stat-item">
              <span>创建时间</span>
              <strong>{formatDate(dataset.created_at)}</strong>
            </div>
            <div className="stat-item">
              <span>修改时间</span>
              <strong>{formatDate(dataset.modified_at)}</strong>
            </div>
          </div>

          <h4>预览（前 10 条）</h4>

          {loading ? (
            <div>预览加载中...</div>
          ) : preview.length === 0 ? (
            <div className="empty-state">暂无可预览内容</div>
          ) : (
            <div className="preview-table">
              <table className="task-table">
                <thead>
                  <tr>
                    {Object.keys(preview[0]).map((key) => (
                      <th key={key}>{key}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.map((row, index) => (
                    <tr key={index}>
                      {Object.values(row).map((value, i) => (
                        <td key={i}>
                          {typeof value === "string" && value.length > 100
                            ? `${value.substring(0, 100)}...`
                            : String(value)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
