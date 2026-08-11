-- Расширение PostgreSQL, активируемое при первом старте контейнера.
-- pg_trgm — fuzzy-поиск (similarity() / % оператор) для item_name/supplier.
-- Qdrant/Ollama/pgvector удалены, поэтому vector-расширение не включаем.
CREATE EXTENSION IF NOT EXISTS pg_trgm;