import { useState } from 'react';
import { Upload } from 'lucide-react';
import { api } from '@/api';
import type { FileResponse } from '@/types/api';

interface Props {
  /** Книга, которую ждёт пункт, — подсказка в шапке панели. */
  expectFilename?: string;
  hint: string;
  /** Вызывается после итогового статуса разбора: карточка перезапускает свои проверки. */
  onSettled?: (file: FileResponse) => void;
}

const POLL_MS = 2000;
const TIMEOUT_MS = 180_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

/**
 * Загрузка книги прямо в карточке пункта: разбор асинхронный, поэтому панель
 * дожидается итогового статуса и сразу показывает листы, хэш и ошибку — вместо
 * похода на страницу «Файлы» посреди прогона ПМИ. Отказы (чужой тип, размер)
 * приходят тем же путём, который проверяет А-2, и показываются как есть.
 */
export default function AnnexUploader({ expectFilename, hint, onSettled }: Props) {
  const [picked, setPicked] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [result, setResult] = useState<FileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const upload = async () => {
    if (!picked) return;
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      setProgress(`Отправляем ${picked.name}…`);
      let file = (await api.uploadFile(picked)).file;
      setProgress(`Зарегистрирован id ${file.id} · статус ${file.status} · ждём разбор…`);
      const deadline = Date.now() + TIMEOUT_MS;
      while (file.status !== 'processed' && file.status !== 'error' && Date.now() < deadline) {
        await sleep(POLL_MS);
        file = await api.getFile(file.id);
        setProgress(`Разбор: статус ${file.status} · листов ${file.total_sheets}`);
      }
      setResult(file);
      setProgress('');
      onSettled?.(file);
    } catch (e) {
      setError((e as Error).message);
      setProgress('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="up">
      <summary className="up__summary">
        <Upload size={15} />
        <span className="up__title">Загрузить книгу прямо здесь</span>
        {expectFilename && <code className="up__expect">{expectFilename}</code>}
      </summary>

      <div className="up__body">
        <div className="up__hint">{hint}</div>

        <div className="up__row">
          <label className="annex__btn annex__btn--probe annex__btn--file" htmlFor="annex-uploader-input">
            <input
              id="annex-uploader-input"
              type="file"
              accept=".xlsx,.xls"
              onChange={(e) => {
                setPicked(e.target.files?.[0] ?? null);
                setResult(null);
                setError(null);
              }}
            />
            <span>Выбрать .xlsx</span>
          </label>
          <button
            type="button"
            className="annex__btn annex__btn--probe"
            onClick={upload}
            disabled={!picked || busy}
            title="POST /api/files/upload, затем GET /api/files/{id} до итогового статуса"
          >
            <Upload size={14} />
            <span>{busy ? 'Загружаем и разбираем…' : 'Загрузить и разобрать'}</span>
          </button>
        </div>

        <div className="up__name">
          {picked ? `${picked.name} · ${(picked.size / 1024 / 1024).toFixed(2)} MiB` : 'файл не выбран'}
        </div>

        {progress && <div className="up__progress">{progress}</div>}

        {result && (
          <ul className="up__lines">
            <li>
              id <code>{result.id}</code> · статус <code>{result.status}</code> · листов{' '}
              {result.total_sheets} · ячеек {result.total_cells}
            </li>
            <li>
              хэш <code>{result.file_hash.slice(0, 16)}…</code> · повторная загрузка той же книги
              даёт тот же id
            </li>
            {result.error_message && <li>ошибка разбора: {result.error_message}</li>}
            <li>
              Проверки пункта ниже видят уже загруженную книгу; список файлов — <code>/files</code>.
            </li>
          </ul>
        )}

        {error && <div className="up__error">{error}</div>}
      </div>
    </details>
  );
}
