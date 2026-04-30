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
      const errorMsg = "Only JSONL files are supported";
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
      const errorMsg = err instanceof Error ? err.message : "Upload failed";
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
            <span>Uploading dataset...</span>
          </div>
        ) : (
          <>
            <div className="upload-icon">📁</div>
            <div className="upload-text">
              <strong>Drop your JSONL file here</strong>
              <span>or click to browse</span>
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
        <p>Accepted format: JSONL</p>
        <p>Required field: <code>user_input</code></p>
        <p>Optional fields: <code>response</code>, <code>reference</code>, <code>retrieved_contexts</code></p>
      </div>
    </div>
  );
}
