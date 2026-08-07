import type { ReactNode } from 'react';

interface EmptyStateProps {
  icon?: ReactNode;
  text: string;
}

export default function EmptyState({ icon, text }: EmptyStateProps) {
  return (
    <div className="empty-state">
      {icon && <div className="empty-state__icon">{icon}</div>}
      <div className="empty-state__text">{text}</div>
    </div>
  );
}