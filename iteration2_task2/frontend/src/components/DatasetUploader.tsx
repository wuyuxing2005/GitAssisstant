import { useState, useCallback } from "react";
import { uploadDataset } from "../services/api";

interface DatasetUploaderProps {
  onUploadComplete?: (result: { message: string; dataset_name: string; line_count: number }) => void;
  onError?: (error: string) => void;
}

export function DatasetUploader({ onUploadComplete, onError }: DatasetUploaderProps) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = useCallback(async (file: File) => {
    if (!file.name.endsWith('.jsonl')) {
      const errorMsg = "仅支持 JSONL 文件";
      setError(errorMsg);
      onError?.(errorMsg);
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const result = await uploadDataset(file);
      setUploading(false);
      onUploadComplete?.(result);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "上传失败";
      setError(errorMsg);
      setUploading(false);
      onError?.(errorMsg);
    }
  }, [onUploadComplete, onError]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleUpload(files[0]);
    }
  }, [handleUpload]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleUpload(files[0]);
    }
  }, [handleUpload]);

  return (
    <div className="dataset-uploader">
      <div
        className={`upload-dropzone ${dragOver ? "drag-over" : ""} ${uploading ? "uploading" : ""}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        {uploading ? (
          <div className="upload-progress">
            <div className="spinner"></div>
            <span>数据集上传中...</span>
          </div>
        ) : (
          <>
            <div className="upload-icon">📁</div>
            <div className="upload-text">
              <strong>将 JSONL 文件拖到这里</strong>
              <span>或点击选择文件</span>
            </div>
            <input
              type="file"
              accept=".jsonl"
              onChange={handleFileInput}
              className="file-input"
              disabled={uploading}
            />
          </>
        )}
      </div>

      {error && (
        <div className="upload-error">
          <span className="error-icon">!</span>
          <span>{error}</span>
        </div>
      )}

      <div className="upload-hints">
        <p>支持格式：JSONL</p>
        <p>必填字段：<code>user_input</code></p>
        <p>常用字段：<code>response</code>、<code>reference</code>、<code>retrieved_contexts</code></p>
      </div>
    </div>
  );
}
