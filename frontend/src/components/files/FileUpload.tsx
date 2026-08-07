import { useRef, useState } from 'react';
import { UploadCloud } from 'lucide-react';
import { motion } from 'framer-motion';

interface FileUploadProps {
  onUpload: (file: File) => Promise<void>;
  compact?: boolean;
}

export default function FileUpload({ onUpload, compact = false }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selected, setSelected] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);

  const selectFile = (file: File | null) => {
    if (file && (file.name.endsWith('.xlsx') || file.name.endsWith('.xls'))) {
      setSelected(file);
    }
  };

  const handleSubmit = async () => {
    if (!selected) return;
    setLoading(true);
    try {
      await onUpload(selected);
      setSelected(null);
      if (inputRef.current) inputRef.current.value = '';
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`upload-form${compact ? ' upload-form--compact' : ''}`}>
      <motion.div
        className={`upload-form__dropzone${dragging ? ' upload-form__dropzone--dragover' : ''}`}
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          selectFile(e.dataTransfer.files[0]);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xls"
          hidden
          onChange={(e) => selectFile(e.target.files?.[0] ?? null)}
        />
        <UploadCloud size={28} className="upload-form__icon" />
        <span>{selected ? selected.name : compact ? 'Выбрать файл' : 'Выберите файл или перетащите сюда'}</span>
        <span className="upload-form__hint">.xlsx / .xls до 50 МБ</span>
      </motion.div>
      <button
        className="btn btn--primary btn--full"
        onClick={handleSubmit}
        disabled={!selected || loading}
      >
        {loading ? '⏳ Загрузка...' : '⬆ Загрузить'}
      </button>
    </div>
  );
}