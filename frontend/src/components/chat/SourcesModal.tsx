import type { SourceInfo } from '@/types/api';
import Modal from '@/components/ui/Modal';

interface SourceListProps {
  sources: SourceInfo[];
}

export function SourceList({ sources }: SourceListProps) {
  return (
    <div className="sources-list">
      {sources.map((s, i) => (
        <div className="source-item" key={`${s.rank}-${i}`}>
          <div className="source-item__header">
            <span className="source-item__rank">#{s.rank || i + 1}</span>
            <span className="source-item__score">Score: {(s.score * 100).toFixed(1)}%</span>
            <span className="source-item__type">{s.source_type || ''}</span>
          </div>
          <div className="source-item__text">{s.chunk}</div>
        </div>
      ))}
    </div>
  );
}

interface SourcesModalProps {
  open: boolean;
  sources: SourceInfo[];
  onClose: () => void;
}

export default function SourcesModal({ open, sources, onClose }: SourcesModalProps) {
  return (
    <Modal open={open} title="📚 Источники" onClose={onClose}>
      <SourceList sources={sources} />
    </Modal>
  );
}