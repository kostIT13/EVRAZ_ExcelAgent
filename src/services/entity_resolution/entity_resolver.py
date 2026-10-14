from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db.database import async_session_maker
from src.core.logging_settings import logger
from src.core.material_synonyms import material_noun_from_adjective

# Верхний предел кандидатов, отдаваемых в Planner/CodeGen
DEFAULT_TOP_N = 10

# Порог pg_trgm similarity (0..1). Снижен для устойчивости к опечаткам.
TRIGRAM_THRESHOLD = 0.25

# Сколько уникальных сущностей отдавать в промпт, если pg_trgm не помог.
MAX_ENTITIES_FOR_PROMPT = 200

# Стоп-слова, не несущие смысла для поиска сущностей (item_name/supplier).
# Нужны, чтобы word-level поиск не «зашумлялся» общими терминами вопроса.
_QUERY_STOPWORDS = {
    # вопросительные слова
    "какова", "каков", "какой", "какая", "какие", "какое", "сколько",
    "чему", "чем", "что", "кто", "где", "когда",
    # глаголы/связки
    "была", "был", "было", "были", "есть", "составила", "составил",
    "составило", "составили", "равна", "равнялась", "равнялось",
    "зафиксирована", "выросла", "вырос", "изменилась", "изменился",
    "покажи", "показать", "дай", "найди", "найти", "сравни", "сравнить",
    # общие термины
    "цена", "цены", "цену", "цене", "ценой", "цен", "стоимость",
    "стоимости", "стоимостью", "руб", "рубль", "рублей", "тн", "тонн",
    "тонна", "тонны", "данным", "данные", "данных", "компании",
    "компания", "компанию", "фирмы", "фирма",
    # предлоги/союзы/частицы
    "за", "в", "во", "на", "по", "с", "со", "и", "или", "от", "до",
    "для", "к", "ко", "о", "об", "при", "из", "у", "же", "ли", "не",
    # периоды
    "месяц", "месяца", "месяцев", "месяцы", "год", "года", "году",
    "годы", "годов", "весь", "вся", "все", "всего", "всей",
    # агрегации
    "минимальная", "минимальной", "минимальную", "минимальный",
    "максимальная", "максимальной", "максимальную", "максимальный",
    "средняя", "средней", "среднюю", "средний", "сумма", "суммарная",
    "суммарный", "дельта", "разница", "разницу", "разность",
    # типы цен
    "среднерыночная", "среднерыночной", "среднерыночную",
    "аукцион", "аукциона", "аукционе", "аукциону", "стартовая",
    "стартовой", "стартовую", "победителя", "победитель", "поставщик",
    "поставщика", "поставщику", "предложения", "предложение",
    "результатам", "результатов", "результате",
    # латиница
    "the", "and", "for", "with",
}


def _extract_query_words(query: str, max_words: int = 10) -> List[str]:
    """Извлекает значимые слова из вопроса для word-level поиска сущностей.

    Раньше pg_trgm сравнивал item_name со ВСЕМ вопросом целиком — для длинных
    вопросов similarity падала ниже порога, и кандидаты не находились (например,
    «цинковый лом» не матчился с item_name «Лом цинка»). Теперь ищем по отдельным
    значимым словам и суммируем similarity.
    """
    words = re.findall(r"[а-яёa-z0-9]+", query.lower())
    out: List[str] = []
    seen: set[str] = set()
    for w in words:
        if len(w) < 3 or w in _QUERY_STOPWORDS or w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= max_words:
            break
    return out


def _expand_query_words(words: List[str]) -> List[str]:
    """Расширяет слова вопроса синонимами материалов.

    «цинковый» -> «цинк», «медный» -> «медь», «алюминиевый» -> «алюминий»,
    чтобы pg_trgm находил «Лом цинка» по запросу «цинковый лом» (прилагательное
    + лом == лом + родительный падеж существительного).
    """
    out = list(words)
    for w in words:
        noun = material_noun_from_adjective(w)
        if noun and noun not in out:
            out.append(noun)
    return out


@dataclass
class EntityCandidate:
    entity_type: str          
    entity_value: str
    score: float
    method: str               

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "entity_value": self.entity_value,
            "score": round(self.score, 4),
            "method": self.method,
        }


class EntityResolver:

    def __init__(self) -> None:
        self._entity_cache: Dict[str, List[str]] = {}
        self._cache_loaded = False

    async def index_entities(
        self,
        items: List[str],
        suppliers: List[str],
        periods: List[str],
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, int]:
        self._entity_cache["item"] = _unique(items)
        self._entity_cache["supplier"] = _unique(suppliers)
        self._entity_cache["period"] = _unique(periods)
        self._cache_loaded = True

        counts = {k: len(v) for k, v in self._entity_cache.items()}
        logger.info(
            "Entity catalog indexed (no embeddings): item={}, supplier={}, period={}",
            counts.get("item", 0),
            counts.get("supplier", 0),
            counts.get("period", 0),
        )
        return counts

    async def resolve_candidates(
        self,
        query: str,
        top_n: int = DEFAULT_TOP_N,
        session: Optional[AsyncSession] = None,
    ) -> List[EntityCandidate]:
        if not query.strip():
            return []

        # Word-level поиск: сравниваем item_name/supplier с отдельными значимыми
        # словами вопроса (а не со всем вопросом), суммируя similarity. Это
        # позволяет находить «Лом цинка» по запросу «цинковый лом».
        words = _extract_query_words(query)
        # Расширяем синонимами материалов: «цинковый» -> «цинк» и т.п.
        words = _expand_query_words(words)
        if not words:
            words = [query.strip()]

        own_session = session is None
        s = session or async_session_maker()
        try:
            sql = text(
                """
                WITH q_words AS (
                    SELECT DISTINCT lower(trim(w)) AS word
                    FROM unnest(string_to_array(:words, ',')) AS w
                    WHERE length(trim(w)) >= 3
                ),
                -- Сначала схлопываем дубликаты строк (item_name повторяется по
                -- месяцам/поставщикам/типам цен), чтобы score отражал РЕЛЕВАНТНОСТЬ,
                -- а не количество строк. Иначе «Лом латуни» (много строк) всегда
                -- обгоняет «Лом цинка» (мало строк) даже для запроса про цинк.
                item_scores AS (
                    SELECT DISTINCT pf.item_name, qw.word,
                           similarity(pf.item_name, qw.word) AS sim
                    FROM mart.price_facts pf
                    CROSS JOIN q_words qw
                    WHERE similarity(pf.item_name, qw.word) >= :threshold
                )
                SELECT 'item' AS entity_type, item_name AS entity_value,
                       SUM(sim) AS score
                FROM item_scores
                GROUP BY item_name
                UNION ALL
                SELECT 'supplier', pf.supplier,
                       SUM(similarity(pf.supplier, qw.word))
                FROM mart.price_facts pf
                CROSS JOIN q_words qw
                WHERE similarity(pf.supplier, qw.word) >= :threshold
                  AND pf.supplier IS NOT NULL
                GROUP BY pf.supplier
                UNION ALL
                SELECT 'supplier', m.dimension,
                       SUM(similarity(m.dimension, qw.word))
                FROM mart.metrics m
                CROSS JOIN q_words qw
                WHERE similarity(m.dimension, qw.word) >= :threshold
                  AND m.dimension IS NOT NULL
                  AND m.dimension <> 'сводная_строка'
                GROUP BY m.dimension
                ORDER BY score DESC
                LIMIT :top_n
                """
            )
            result = await s.execute(
                sql,
                {
                    "words": ",".join(words),
                    "threshold": TRIGRAM_THRESHOLD,
                    "top_n": top_n,
                },
            )
            rows = result.all()
        finally:
            if own_session:
                await s.close()

        candidates = [
            EntityCandidate(
                entity_type=r.entity_type,
                entity_value=r.entity_value,
                score=float(r.score or 0.0),
                method="trigram",
            )
            for r in rows
        ]
        return candidates[:top_n]

    def entities_for_prompt(self) -> Dict[str, List[str]]:
        if not self._cache_loaded:
            return {}
        return {
            "item_name": self._entity_cache.get("item", [])[:MAX_ENTITIES_FOR_PROMPT],
            "supplier": self._entity_cache.get("supplier", [])[:MAX_ENTITIES_FOR_PROMPT],
            "sheet_period": self._entity_cache.get("period", [])[:MAX_ENTITIES_FOR_PROMPT],
        }


def _unique(values: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for v in values:
        key = str(v).strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


entity_resolver: EntityResolver = EntityResolver()