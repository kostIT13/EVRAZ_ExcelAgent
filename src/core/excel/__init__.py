"""Excel parsing and normalization.

Components
----------
- ``parser`` — чтение Excel (openpyxl) в ParsedFile.
- ``normalize`` — нормализация заголовков/типов колонок.
- ``table_structurer`` — структурирование в факты цен.
- ``schema_inference`` — LLM-распознавание структуры листов (разовые).
- ``template_fingerprint`` — отпечаток структуры листа для кэша схем.
- ``comment_extractor`` — извлечение комментариев.
"""