# -*- coding: utf-8 -*-
"""Генерация обновлённой презентации EVRAZ Agent (расширенная версия).

Создаёт data/EVRAZ_Agent_updated.pptx — 35 слайдов, 8 разделов,
в фирменном стиле EVRAZ (тёмная тема + оранжевый акцент).
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# ---------------------------------------------------------------------------
# Палитра (соответствует исходной презентации)
# ---------------------------------------------------------------------------
BG = RGBColor(0x1B, 0x1F, 0x24)          # основной фон
BG_DARK = RGBColor(0x26, 0x2C, 0x33)     # фон титула / разделителей
ACCENT = RGBColor(0xFF, 0x5A, 0x36)      # оранжевый EVRAZ
ACCENT_LIGHT = RGBColor(0xFF, 0xB1, 0x99)
BLUE = RGBColor(0x1C, 0x72, 0x93)        # синий (метки разделов)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GRAY = RGBColor(0x8A, 0x97, 0xA6)        # вторичный текст на тёмном
GRAY_DARK = RGBColor(0x5B, 0x67, 0x73)   # вторичный текст на светлом
CARD_BORDER = RGBColor(0x3D, 0x4A, 0x57)
CARD_BORDER_LIGHT = RGBColor(0xE3, 0xE6, 0xE9)
TEXT_DARK = RGBColor(0x1B, 0x1F, 0x24)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
RED = RGBColor(0xC6, 0x28, 0x28)
ZEBRA = RGBColor(0xF0, 0xF2, 0xF5)
LIGHT_CARD = RGBColor(0xF5, 0xF6, 0xF8)

FONT = "Calibri"
MONO = "Consolas"

W_IN = 13.333
H_IN = 7.5

prs = Presentation()
prs.slide_width = Inches(W_IN)
prs.slide_height = Inches(H_IN)
BLANK = prs.slide_layouts[6]

PAGE = [0]  # счётчик страниц


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def _new_slide():
    return prs.slides.add_slide(BLANK)


def set_bg(slide, color=BG):
    sp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    sp.fill.solid()
    sp.fill.fore_color.rgb = color
    sp.line.fill.background()
    sp.shadow.inherit = False
    return sp


def add_rect(slide, x, y, w, h, fill=None, line=None, line_w=1.0,
             shape=MSO_SHAPE.RECTANGLE, radius=None):
    sp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line
        sp.line.width = Pt(line_w)
    sp.shadow.inherit = False
    if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        try:
            sp.adjustments[0] = radius
        except Exception:  # noqa: BLE001
            pass
    return sp


def add_text(slide, x, y, w, h, text, size=18, color=WHITE, bold=False,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font=FONT,
             line_spacing=1.0, wrap=True, italic=False):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = line_spacing
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = font
    return tb


def add_paras(slide, x, y, w, h, paras, anchor=MSO_ANCHOR.TOP, wrap=True):
    """paras: список dict {runs: [(text, size, color, bold)], align, space_before, space_after, line_spacing}"""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = para.get("align", PP_ALIGN.LEFT)
        p.line_spacing = para.get("line_spacing", 1.0)
        if para.get("space_before") is not None:
            p.space_before = Pt(para["space_before"])
        if para.get("space_after") is not None:
            p.space_after = Pt(para["space_after"])
        for (text, size, color, bold) in para["runs"]:
            run = p.add_run()
            run.text = text
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = color
            run.font.name = FONT
    return tb


def add_card(slide, x, y, w, h, title=None, body=None, number=None,
             title_color=WHITE, body_color=GRAY, fill=BG_DARK, line=CARD_BORDER,
             title_size=16, body_size=12, number_color=ACCENT, body_align=PP_ALIGN.LEFT):
    add_rect(slide, x, y, w, h, fill=fill, line=line, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.07)
    ty = y + 0.18
    if number is not None:
        add_text(slide, x + 0.22, ty, 0.6, 0.45, str(number), size=22,
                 color=number_color, bold=True)
        tx = x + 0.75
        tw = w - 0.95
    else:
        tx = x + 0.22
        tw = w - 0.44
    if title:
        add_text(slide, tx, ty, tw, 0.4, title, size=title_size, color=title_color, bold=True)
        ty += 0.42
    if body:
        add_text(slide, tx, ty, tw, h - (ty - y) - 0.2, body, size=body_size,
                 color=body_color, line_spacing=1.12, align=body_align)
    return


def add_header(slide, section, title, page_num=None):
    add_rect(slide, 0.6, 0.5, 0.5, 0.07, fill=ACCENT)
    add_text(slide, 0.6, 0.62, 9, 0.3, section.upper(), size=12, color=BLUE, bold=True)
    add_text(slide, 0.6, 0.95, 12.1, 0.75, title, size=30, color=WHITE, bold=True)
    add_text(slide, 0.6, 7.08, 4, 0.3, "EVRAZ Agent", size=10, color=GRAY)
    if page_num is not None:
        add_text(slide, 11.9, 7.08, 0.85, 0.3, str(page_num), size=10,
                 color=GRAY, align=PP_ALIGN.RIGHT)


def add_footer(slide, page_num=None):
    add_text(slide, 0.6, 7.08, 4, 0.3, "EVRAZ Agent", size=10, color=GRAY)
    if page_num is not None:
        add_text(slide, 11.9, 7.08, 0.85, 0.3, str(page_num), size=10,
                 color=GRAY, align=PP_ALIGN.RIGHT)


def add_arrow(slide, x1, y1, x2, y2, color=ACCENT, width=1.5, dash=None, head=True):
    """Прямая стрелка-коннектор с наконечником."""
    from pptx.enum.shapes import MSO_CONNECTOR
    from pptx.oxml.ns import qn
    conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                      Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    conn.line.color.rgb = color
    conn.line.width = Pt(width)
    conn.shadow.inherit = False
    ln = conn.line._get_or_add_ln()
    if dash:
        d = ln.makeelement(qn("a:prstDash"), {"val": dash})
        ln.append(d)
    if head:
        tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
        ln.append(tail)
    return conn


def add_elbow(slide, x1, y1, x2, y2, color=ACCENT, width=1.5, dash=None, head=True):
    """Г-образный коннектор со стрелкой."""
    from pptx.enum.shapes import MSO_CONNECTOR
    from pptx.oxml.ns import qn
    conn = slide.shapes.add_connector(MSO_CONNECTOR.ELBOW,
                                      Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    conn.line.color.rgb = color
    conn.line.width = Pt(width)
    conn.shadow.inherit = False
    ln = conn.line._get_or_add_ln()
    if dash:
        d = ln.makeelement(qn("a:prstDash"), {"val": dash})
        ln.append(d)
    if head:
        tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
        ln.append(tail)
    return conn


def add_entity_box(slide, x, y, w, h, name, fields, header_fill=BLUE, body_size=8.5):
    """Блок сущности для ER-диаграммы: заголовок + поля."""
    add_rect(slide, x, y, w, h, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
    add_rect(slide, x, y, w, 0.32, fill=header_fill, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
    add_text(slide, x + 0.08, y + 0.04, w - 0.16, 0.26, name, size=10, color=WHITE,
             bold=True, align=PP_ALIGN.CENTER)
    paras = []
    for f in fields:
        paras.append({"runs": [(f, body_size, GRAY, False)], "line_spacing": 1.0})
    add_paras(slide, x + 0.1, y + 0.4, w - 0.2, h - 0.5, paras)


def add_table(slide, data, x, y, w, col_widths, row_height=0.42,
              header_fill=BLUE, header_color=WHITE, body_size=12, header_size=12,
              first_col_bold=False, zebra=True, align_first=PP_ALIGN.LEFT):
    rows = len(data)
    cols = len(data[0])
    gframe = slide.shapes.add_table(rows, cols, Inches(x), Inches(y),
                                    Inches(w), Inches(row_height * rows))
    table = gframe.table
    for c, cw in enumerate(col_widths):
        table.columns[c].width = Inches(cw)
    for r in range(rows):
        table.rows[r].height = Inches(row_height)
        for c in range(cols):
            cell = table.cell(r, c)
            cell.margin_left = Inches(0.1)
            cell.margin_right = Inches(0.1)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = align_first if c == 0 else PP_ALIGN.LEFT
            run = p.add_run()
            run.text = str(data[r][c])
            run.font.name = FONT
            if r == 0:
                run.font.size = Pt(header_size)
                run.font.bold = True
                run.font.color.rgb = header_color
                cell.fill.solid()
                cell.fill.fore_color.rgb = header_fill
            else:
                run.font.size = Pt(body_size)
                run.font.bold = first_col_bold and c == 0
                run.font.color.rgb = TEXT_DARK
                if zebra and r % 2 == 0:
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = ZEBRA
                else:
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = WHITE
    return table


def add_section_divider(number, title, subtitle, page_num=None):
    slide = _new_slide()
    set_bg(slide, BG_DARK)
    add_text(slide, 0.8, 1.5, 3.5, 2.6, number, size=130, color=ACCENT, bold=True)
    add_rect(slide, 0.9, 4.35, 1.2, 0.08, fill=ACCENT)
    add_text(slide, 0.9, 4.55, 11.5, 0.9, title, size=40, color=WHITE, bold=True)
    add_text(slide, 0.9, 5.5, 11.5, 0.7, subtitle, size=18, color=GRAY, line_spacing=1.15)
    add_footer(slide, page_num)
    return slide


def next_page():
    PAGE[0] += 1
    return PAGE[0]


# ---------------------------------------------------------------------------
# СЛАЙД 1 — Титульный
# ---------------------------------------------------------------------------
def slide_title():
    slide = _new_slide()
    set_bg(slide, BG_DARK)
    # декоративные оранжевые элементы
    add_rect(slide, 0, 0, 0.18, H_IN, fill=ACCENT)
    add_rect(slide, 9.6, 0, 3.73, 0.18, fill=ACCENT)
    add_rect(slide, 9.6, 0.18, 0.18, 2.2, fill=ACCENT)
    add_rect(slide, 12.0, 2.0, 1.33, 0.18, fill=ACCENT)
    add_rect(slide, 0.6, 2.35, 0.5, 0.07, fill=ACCENT)
    add_text(slide, 0.6, 2.5, 9, 0.4, "EVRAZ  ·  ДЕМОНСТРАЦИЯ ПРОЕКТА", size=14,
             color=ACCENT_LIGHT, bold=True)
    add_text(slide, 0.6, 2.95, 12, 1.2, "EVRAZ Agent", size=60, color=WHITE, bold=True)
    add_text(slide, 0.6, 4.15, 11.5, 0.6,
             "AI-агент для работы с Excel-файлами металлургической компании", size=20,
             color=GRAY)
    # карточки Backend / Frontend
    add_rect(slide, 0.6, 5.15, 5.9, 1.35, fill=BG, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_text(slide, 0.85, 5.35, 5.4, 0.4, "Backend", size=16, color=WHITE, bold=True)
    add_text(slide, 0.85, 5.75, 5.4, 0.5, "Python 3.12 · FastAPI · LangGraph · PostgreSQL",
             size=13, color=GRAY)
    add_rect(slide, 6.85, 5.15, 5.9, 1.35, fill=BG, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_text(slide, 7.1, 5.35, 5.4, 0.4, "Frontend", size=16, color=WHITE, bold=True)
    add_text(slide, 7.1, 5.75, 5.4, 0.5, "React 18 · TypeScript · Vite", size=13, color=GRAY)
    add_footer(slide, next_page())


# ---------------------------------------------------------------------------
# СЛАЙД 2 — Оглавление
# ---------------------------------------------------------------------------
def slide_toc():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Введение", "Содержание", next_page())
    items = [
        ("01", "Введение", "О проекте · Проблематика · Задача и цели"),
        ("02", "Решение и архитектура", "Обзор · Архитектура · Стек · Структура"),
        ("03", "Обработка данных", "Пайплайн · Парсинг · Витрина · Схема БД"),
        ("04", "LLM-агент", "LangGraph · Узлы · Безопасный SQL · Entity Resolution"),
        ("05", "Интерфейс и наблюдаемость", "Frontend · Метрики · Безопасность"),
        ("06", "Качество", "Тесты · Golden dataset · CI/CD"),
        ("07", "Демонстрация и развёртывание", "Сценарий · Docker · Быстрый старт"),
        ("08", "Итоги", "Результаты · Перспективы"),
    ]
    for i, (num, title, sub) in enumerate(items):
        col = i // 4
        row = i % 4
        x = 0.6 + col * 6.15
        y = 1.95 + row * 1.22
        add_rect(slide, x, y, 5.9, 1.05, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
        add_text(slide, x + 0.2, y + 0.18, 0.7, 0.6, num, size=22, color=ACCENT, bold=True)
        add_text(slide, x + 0.95, y + 0.16, 4.8, 0.4, title, size=15, color=WHITE, bold=True)
        add_text(slide, x + 0.95, y + 0.55, 4.8, 0.4, sub, size=11, color=GRAY)


# ---------------------------------------------------------------------------
# СЛАЙД 3 — О проекте
# ---------------------------------------------------------------------------
def slide_about():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Введение", "О проекте", next_page())
    add_paras(slide, 0.6, 1.9, 12.1, 1.5, [
        {"runs": [
            ("EVRAZ Agent", 18, WHITE, True),
            (" — агентная система «вопрос–ответ» по данным из Excel-файлов с ценами на цветные металлы (лом). "
             "Пользователь загружает Excel-файлы, система парсит их, нормализует в факт-таблицы витрины данных, "
             "а затем через LLM-агента отвечает на естественно-языковые вопросы, генерируя и выполняя безопасный "
             "SQL-запрос к PostgreSQL.", 16, GRAY, False),
        ], "line_spacing": 1.25},
    ])
    cards = [
        ("Вопрос–ответ", "Естественный язык → точный ответ с данными, SQL и источниками"),
        ("LLM-агент", "LangGraph: классификация → планирование → генерация SQL → проверка"),
        ("Безопасный SQL", "Только SELECT, whitelist таблиц, валидация, read-only выполнение"),
        ("Prod-ready", "Асинхронный ingestion, auth, rate limiting, мониторинг, golden-тесты"),
    ]
    for i, (t, b) in enumerate(cards):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 3.6 + row * 1.6
        add_card(slide, x, y, 5.9, 1.4, title=t, body=b, title_size=16, body_size=13)


# ---------------------------------------------------------------------------
# СЛАЙД 4 — Проблематика
# ---------------------------------------------------------------------------
def slide_problem():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Введение", "Проблематика", next_page())
    cards = [
        ("1", "Разные форматы", "Ежедневные Excel-файлы с ценами на цветные металлы (лом) — десятки листов, разные форматы."),
        ("2", "«Грязные» файлы", "Сдвинутые шапки, объединённые ячейки, вложенные заголовки."),
        ("3", "Простой язык", "Бизнес-пользователи хотят отвечать на вопросы простым языком, а не разбираться в таблицах."),
        ("4", "Коммерческая тайна", "Цены — конфиденциальные данные: они не должны утекать наружу."),
    ]
    for i, (num, t, b) in enumerate(cards):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 1.95 + row * 1.75
        add_card(slide, x, y, 5.9, 1.55, number=num, title=t, body=b,
                 title_size=16, body_size=13)
    add_rect(slide, 0.6, 5.7, 12.1, 0.95, fill=ACCENT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, 0.9, 5.95, 11.5, 0.5,
             "Результат: менеджер тратит часы на ручной поиск по файлам вместо принятия решений",
             size=16, color=WHITE, bold=True)


# ---------------------------------------------------------------------------
# СЛАЙД 5 — Задача и цели
# ---------------------------------------------------------------------------
def slide_goal():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Введение", "Задача и цели", next_page())
    add_text(slide, 0.6, 1.9, 12.1, 0.5,
             "Построить prod-ready систему «вопрос–ответ» по Excel-данным", size=20,
             color=WHITE, bold=True)
    cards = [
        ("1", "Загрузил файл", "Система сама распарсила и нормализовала данные"),
        ("2", "Задал вопрос", "На естественном языке — получил ответ с данными"),
        ("3", "Прозрачность", "Видно, какой SQL выполнен и откуда взялись цифры"),
        ("4", "Безопасность", "Только чтение, только проверенные таблицы, без утечки данных"),
    ]
    for i, (num, t, b) in enumerate(cards):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 2.6 + row * 1.6
        add_card(slide, x, y, 5.9, 1.4, number=num, title=t, body=b,
                 title_size=16, body_size=13, number_color=BLUE)
    add_rect(slide, 0.6, 6.0, 12.1, 0.8, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, 0.9, 6.22, 11.5, 0.4,
             "Цель: точность ≥ 85% на ключевых типах запросов при полной traceability ответа",
             size=16, color=ACCENT_LIGHT, bold=True)


# ---------------------------------------------------------------------------
# СЛАЙД 6 — Разделитель: Решение и архитектура
# ---------------------------------------------------------------------------
def slide_div_arch():
    add_section_divider("02", "Решение и архитектура",
                        "Обзор решения, архитектура системы, технологический стек и структура проекта",
                        next_page())


# ---------------------------------------------------------------------------
# СЛАЙД 7 — Решение — обзор
# ---------------------------------------------------------------------------
def slide_solution():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Решение и архитектура", "Решение — обзор", next_page())
    # поток
    steps = [
        ("Excel", "файл"),
        ("Парсинг", "src/core/excel"),
        ("RAW", "таблицы"),
        ("Нормализация", "mart"),
        ("LangGraph", "агент"),
        ("Безопасный", "SELECT"),
    ]
    n = len(steps)
    box_w = 1.75
    gap = 0.28
    total = n * box_w + (n - 1) * gap
    x0 = (W_IN - total) / 2
    y = 1.95
    for i, (t, s) in enumerate(steps):
        x = x0 + i * (box_w + gap)
        add_rect(slide, x, y, box_w, 1.15, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
        add_text(slide, x + 0.1, y + 0.2, box_w - 0.2, 0.45, t, size=14, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, x + 0.1, y + 0.65, box_w - 0.2, 0.4, s, size=10, color=GRAY,
                 align=PP_ALIGN.CENTER)
        if i < n - 1:
            add_text(slide, x + box_w - 0.02, y + 0.3, gap + 0.04, 0.5, "→", size=18,
                     color=ACCENT, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, 0.6, 3.4, 12.1, 0.5,
             "Вопрос пользователя → агент планирует и выполняет SQL → ответ + SQL + источники (PostgreSQL)",
             size=14, color=GRAY, align=PP_ALIGN.CENTER)
    # таблица частей
    add_table(slide, [
        ["Часть", "Технологии", "Назначение"],
        ["Backend", "FastAPI, LangGraph, SQLAlchemy", "API, парсинг, агент"],
        ["Frontend", "React 18 + TS + Vite", "Чат, файлы, дашборд, метрики, трейсы"],
        ["Инфраструктура", "Docker Compose, Nginx", "PostgreSQL, Prometheus, Grafana"],
    ], 0.6, 4.1, 12.1, [2.6, 4.6, 4.9], row_height=0.5, body_size=13, header_size=13)


# ---------------------------------------------------------------------------
# СЛАЙД 8 — Архитектура системы
# ---------------------------------------------------------------------------
def slide_architecture():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Решение и архитектура", "Архитектура системы", next_page())
    # блоки
    add_rect(slide, 0.6, 1.95, 3.0, 1.0, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 0.7, 2.15, 2.8, 0.4, "Frontend", size=15, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, 0.7, 2.55, 2.8, 0.3, "React + Vite (Nginx)", size=11, color=GRAY,
             align=PP_ALIGN.CENTER)
    add_rect(slide, 4.0, 1.95, 4.6, 1.0, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 4.1, 2.15, 4.4, 0.4, "Backend — FastAPI (:8000)", size=15, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, 4.1, 2.55, 4.4, 0.3, "роутеры · ingestion · агент · entity-resolution", size=11,
             color=GRAY, align=PP_ALIGN.CENTER)
    add_rect(slide, 9.0, 1.95, 3.7, 1.0, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 9.1, 2.15, 3.5, 0.4, "LLM-провайдер", size=15, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, 9.1, 2.55, 3.5, 0.3, "OpenAI-совместимый API", size=11, color=GRAY,
             align=PP_ALIGN.CENTER)
    # стрелки
    add_text(slide, 3.62, 2.2, 0.4, 0.5, "→", size=18, color=ACCENT, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, 8.62, 2.2, 0.4, 0.5, "→", size=18, color=ACCENT, bold=True, align=PP_ALIGN.CENTER)
    # нижние блоки
    add_rect(slide, 0.6, 3.35, 5.9, 1.0, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 0.7, 3.55, 5.7, 0.4, "PostgreSQL 16", size=15, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, 0.7, 3.95, 5.7, 0.3, "public: files, sheets, cells · mart: price_facts, metrics",
             size=11, color=GRAY, align=PP_ALIGN.CENTER)
    add_rect(slide, 6.85, 3.35, 5.9, 1.0, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 6.95, 3.55, 5.7, 0.4, "Мониторинг", size=15, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, 6.95, 3.95, 5.7, 0.3, "Prometheus :9090 · Grafana :3001", size=11, color=GRAY,
             align=PP_ALIGN.CENTER)
    add_text(slide, 3.62, 3.0, 0.4, 0.5, "↓", size=18, color=ACCENT, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, 9.62, 3.0, 0.4, 0.5, "↓", size=18, color=ACCENT, bold=True, align=PP_ALIGN.CENTER)
    # принципы
    add_text(slide, 0.6, 4.7, 12.1, 0.4, "Ключевые принципы", size=16, color=WHITE, bold=True)
    add_paras(slide, 0.6, 5.15, 12.1, 1.6, [
        {"runs": [("•  ", 14, ACCENT, True),
                  ("Нормализованная long-факт-таблица", 14, WHITE, True),
                  (" — агент генерирует простой SQL поверх mart.price_facts / mart.metrics, без обращения к сырым ячейкам.", 14, GRAY, False)],
         "space_after": 8},
        {"runs": [("•  ", 14, ACCENT, True),
                  ("Детерминированные правки SQL", 14, WHITE, True),
                  (" в codegen_node повышают надёжность LLM-генерации (префиксный поиск, нормализация поставщиков, is_blank → 0/1).", 14, GRAY, False)],
         "space_after": 8},
        {"runs": [("•  ", 14, ACCENT, True),
                  ("Кэш ответов и fallback-логика", 14, WHITE, True),
                  (" верификатора уменьшают количество повторных прогонов графа.", 14, GRAY, False)]},
    ])


# ---------------------------------------------------------------------------
# СЛАЙД 9 — Технологический стек
# ---------------------------------------------------------------------------
def slide_stack():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Решение и архитектура", "Технологический стек", next_page())
    cols = [
        ("Backend (Python ≥ 3.12)", [
            "FastAPI + uvicorn — REST API",
            "LangGraph + checkpoint-postgres",
            "langchain-openai — structured output",
            "SQLAlchemy 2.0 (async) + Alembic",
            "openpyxl, pandas — Excel",
            "rapidfuzz — fuzzy match",
            "loguru, prometheus-client, slowapi",
            "pydantic-settings, python-multipart",
        ]),
        ("Frontend (React)", [
            "React 18 + TypeScript + Vite",
            "react-router-dom — роутинг",
            "chart.js — графики результатов",
            "framer-motion — анимации",
            "lucide-react — иконки",
            "react-markdown — рендер ответов",
        ]),
        ("Инфраструктура (Docker)", [
            "postgres:16-alpine — БД",
            "service — FastAPI (:8000)",
            "frontend — Nginx (:8080)",
            "prometheus — метрики (:9090)",
            "grafana — дашборды (:3001)",
        ]),
    ]
    for i, (title, items) in enumerate(cols):
        x = 0.6 + i * 4.15
        add_rect(slide, x, 1.95, 3.9, 4.7, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
        add_rect(slide, x, 1.95, 3.9, 0.6, fill=BLUE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
        add_text(slide, x + 0.2, 2.1, 3.5, 0.4, title, size=15, color=WHITE, bold=True)
        paras = []
        for it in items:
            paras.append({"runs": [("•  ", 12, ACCENT, True), (it, 12, GRAY, False)],
                          "space_after": 6, "line_spacing": 1.05})
        add_paras(slide, x + 0.2, 2.75, 3.5, 3.8, paras)


# ---------------------------------------------------------------------------
# СЛАЙД 10 — Структура проекта
# ---------------------------------------------------------------------------
def slide_structure():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Решение и архитектура", "Структура проекта", next_page())
    tree = [
        "├── alembic/            # миграции БД",
        "├── data/               # рабочие данные, bm25_index.pkl",
        "├── diagrams/           # Mermaid-диаграммы",
        "├── docs/               # примеры запросов",
        "├── frontend/           # React-приложение",
        "│   └── src/            # pages, components, api, hooks",
        "├── scripts/            # init-db, prometheus, grafana",
        "├── src/                # Backend",
        "│   ├── main.py         # FastAPI app",
        "│   ├── api/            # роутеры (agent, cache, schema, trace)",
        "│   ├── core/           # config, db, excel, metrics",
        "│   └── services/       # agent, llm, mart, excel, entity_resolution",
        "├── tests/              # pytest, golden dataset",
        "└── PROJECT.md          # подробное техническое описание",
    ]
    add_rect(slide, 0.6, 1.95, 7.3, 4.7, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
    paras = []
    for line in tree:
        paras.append({"runs": [(line, 12, GRAY, False)], "line_spacing": 1.12})
    add_paras(slide, 0.85, 2.15, 6.9, 4.3, paras, anchor=MSO_ANCHOR.TOP)
    # правая колонка — назначение ключевых каталогов
    add_text(slide, 8.2, 1.95, 4.5, 0.4, "Ключевые каталоги", size=16, color=WHITE, bold=True)
    right = [
        ("src/services/agent", "LangGraph-граф, узлы, sql_compiler, промпты"),
        ("src/core/excel", "парсер, нормализация, schema_inference"),
        ("src/services/mart", "нормализация в витрину (price_facts, metrics)"),
        ("src/services/llm", "LLMClient, structured output"),
        ("src/services/entity_resolution", "fuzzy-match, query_cache"),
        ("frontend/src/pages", "Chat, Files, Dashboard, Metrics, Trace"),
    ]
    paras = []
    for t, b in right:
        paras.append({"runs": [(t, 13, ACCENT_LIGHT, True)], "space_after": 1})
        paras.append({"runs": [(b, 12, GRAY, False)], "space_after": 10, "line_spacing": 1.05})
    add_paras(slide, 8.2, 2.45, 4.5, 4.2, paras)


# ---------------------------------------------------------------------------
# СЛАЙД 11 — Разделитель: Обработка данных
# ---------------------------------------------------------------------------
def slide_div_data():
    add_section_divider("03", "Обработка данных",
                        "Пайплайн ingestion, парсинг Excel, витрина данных и схема базы данных",
                        next_page())


# ---------------------------------------------------------------------------
# СЛАЙД 12 — Поток обработки файла
# ---------------------------------------------------------------------------
def slide_pipeline():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Обработка данных", "Поток обработки файла", next_page())
    steps = [
        ("1", "Upload", "Файл сохраняется, статус uploaded"),
        ("2", "Ingestion", "Асинхронный парсинг Excel: листы, колонки, ячейки, комментарии"),
        ("3", "Schema Inference", "LLM предлагает схему для новых форматов; известные — по Template Fingerprint без LLM"),
        ("4", "Normalize", "Перенос в витрину данных, идемпотентно — повторная заливка без дублей"),
        ("5", "Entity Resolution", "Сбор справочников сущностей для ответов"),
    ]
    for i, (num, t, b) in enumerate(steps):
        y = 1.95 + i * 0.92
        add_rect(slide, 0.6, y, 0.7, 0.72, fill=ACCENT, shape=MSO_SHAPE.OVAL)
        add_text(slide, 0.6, y + 0.14, 0.7, 0.45, num, size=18, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, 1.55, y + 0.02, 2.6, 0.4, t, size=16, color=WHITE, bold=True)
        add_text(slide, 1.55, y + 0.4, 11.2, 0.4, b, size=12.5, color=GRAY)
    add_rect(slide, 0.6, 6.6, 12.1, 0.55, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.15)
    add_text(slide, 0.9, 6.72, 11.5, 0.35,
             "uploaded  →  processing  →  ready  |  failed", size=15, color=ACCENT_LIGHT,
             bold=True, align=PP_ALIGN.CENTER)


# ---------------------------------------------------------------------------
# СЛАЙД 13 — Парсинг Excel и Schema Inference
# ---------------------------------------------------------------------------
def slide_parsing():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Обработка данных", "Парсинг Excel и Schema Inference", next_page())
    # левая колонка — модули парсинга
    add_text(slide, 0.6, 1.95, 5.8, 0.4, "Модули парсинга (src/core/excel)", size=16,
             color=WHITE, bold=True)
    mods = [
        ("parser.py", "чтение .xlsx через openpyxl/pandas"),
        ("comment_extractor.py", "извлечение комментариев ячеек"),
        ("normalize.py", "нормализация имён листов/колонок"),
        ("schema_inference.py", "авто-определение типов колонок"),
        ("sheet_kind_detector.py", "вид листа: prices / metrics / generic"),
        ("table_structurer.py", "структуризация таблицы"),
        ("template_fingerprint.py", "отпечаток шаблона листа"),
    ]
    paras = []
    for t, b in mods:
        paras.append({"runs": [(t, 13, ACCENT_LIGHT, True)], "space_after": 1})
        paras.append({"runs": [(b, 12, GRAY, False)], "space_after": 8, "line_spacing": 1.0})
    add_paras(slide, 0.6, 2.4, 5.8, 4.3, paras)
    # правая колонка — schema inference flow
    add_text(slide, 6.9, 1.95, 5.8, 0.4, "Schema Inference", size=16, color=WHITE, bold=True)
    flow = [
        ("1", "Fingerprint", "compute_sheet_fingerprint — отпечаток структуры листа"),
        ("2", "Шаблон найден", "схема применяется без LLM (mart.sheet_templates)"),
        ("3", "LLM-инференс", "структурный вывод Pydantic SheetSchema → pending_confirmation"),
        ("4", "Подтверждение", "пользователь правит/подтверждает схему → confirmed"),
    ]
    for i, (num, t, b) in enumerate(flow):
        y = 2.45 + i * 1.05
        add_rect(slide, 6.9, y, 5.8, 0.9, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
        add_text(slide, 7.1, y + 0.1, 0.5, 0.5, num, size=18, color=ACCENT, bold=True)
        add_text(slide, 7.6, y + 0.1, 4.9, 0.35, t, size=14, color=WHITE, bold=True)
        add_text(slide, 7.6, y + 0.45, 4.9, 0.4, b, size=11.5, color=GRAY)


# ---------------------------------------------------------------------------
# СЛАЙД 14 — Витрина данных (mart)
# ---------------------------------------------------------------------------
def slide_mart():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Обработка данных", "Витрина данных (mart)", next_page())
    add_text(slide, 0.6, 1.9, 12.1, 0.4, "mart.price_facts — цены лома", size=16,
             color=WHITE, bold=True)
    add_table(slide, [
        ["Колонка", "Пример"],
        ["sheet_period", "2025-01"],
        ["item_name", "Лом меди марки А"],
        ["supplier", "Сплав-21"],
        ["price_type", "среднерыночная / аукцион_старт / поставщик"],
        ["value, currency, unit", "486 500, ₽, т"],
        ["is_blank", "0/1 (пустые ячейки не превращаются в 0)"],
    ], 0.6, 2.35, 12.1, [3.2, 8.9], row_height=0.4, body_size=12.5, header_size=13)
    add_text(slide, 0.6, 5.15, 12.1, 0.4, "mart.metrics — производственные метрики", size=16,
             color=WHITE, bold=True)
    add_rect(slide, 0.6, 5.6, 12.1, 0.75, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 0.9, 5.78, 11.5, 0.4,
             "dimension · period · metric_type · metric · value · unit · is_blank",
             size=14, color=GRAY, align=PP_ALIGN.CENTER)
    add_rect(slide, 0.6, 6.5, 12.1, 0.6, fill=ACCENT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, 0.9, 6.62, 11.5, 0.4,
             "Long-факт-таблицы: агент генерирует простой SQL без обращения к сырым ячейкам",
             size=14, color=WHITE, bold=True, align=PP_ALIGN.CENTER)


# ---------------------------------------------------------------------------
# СЛАЙД 15 — Схема базы данных
# ---------------------------------------------------------------------------
def slide_db():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Обработка данных", "Схема базы данных", next_page())
    add_text(slide, 0.6, 1.9, 5.8, 0.4, "Схема public", size=16, color=WHITE, bold=True)
    add_table(slide, [
        ["Таблица", "Назначение"],
        ["files", "загруженные файлы (hash, статус)"],
        ["sheets", "листы (имя, период, kind)"],
        ["column_metadata", "колонки листов (тип, роль)"],
        ["cells", "сырые ячейки"],
        ["entity_dictionary", "словарь сущностей"],
        ["excel_comments", "комментарии ячеек"],
        ["query_cache", "кэш вопрос → SQL/результат"],
        ["golden_dataset", "эталонные вопросы"],
        ["query_logs", "журнал запросов и трейсов"],
    ], 0.6, 2.35, 5.9, [2.2, 3.7], row_height=0.36, body_size=11.5, header_size=12)
    add_text(slide, 6.9, 1.9, 5.8, 0.4, "Схема mart", size=16, color=WHITE, bold=True)
    add_table(slide, [
        ["Таблица", "Назначение"],
        ["price_facts", "нормализованные цены лома"],
        ["metrics", "производственные метрики"],
        ["sheet_templates", "шаблоны листов по fingerprint"],
        ["supplier_aliases", "алиасы поставщиков"],
    ], 6.9, 2.35, 5.9, [2.2, 3.7], row_height=0.36, body_size=11.5, header_size=12)
    add_rect(slide, 0.6, 6.15, 12.1, 0.85, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_paras(slide, 0.9, 6.3, 11.5, 0.6, [
        {"runs": [("Особенность: ", 13, WHITE, True),
                  ("булевы поля (is_blank, sheet_kind_auto, is_active) объявлены как Integer (0/1) — "
                   "в SQL их нужно сравнивать с числами, а не с TRUE/FALSE.", 13, GRAY, False)],
         "line_spacing": 1.1},
    ])


# ---------------------------------------------------------------------------
# СЛАЙД 16 — Разделитель: LLM-агент
# ---------------------------------------------------------------------------
def slide_div_agent():
    add_section_divider("04", "LLM-агент",
                        "LangGraph-граф, узлы, безопасная генерация SQL, Entity Resolution и устойчивость LLM",
                        next_page())


# ---------------------------------------------------------------------------
# СЛАЙД 17 — LangGraph-агент
# ---------------------------------------------------------------------------
def slide_agent():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "LLM-агент", "LangGraph-агент", next_page())
    add_text(slide, 0.6, 1.9, 12.1, 0.4,
             "Граф узлов с чекпоинтами в PostgreSQL и ретраями", size=16, color=GRAY)
    nodes = ["Classifier", "Disambig.", "Planner", "CodeGen", "Executor", "Verifier", "Answer"]
    n = len(nodes)
    box_w = 1.5
    gap = 0.22
    total = n * box_w + (n - 1) * gap
    x0 = (W_IN - total) / 2
    y = 2.6
    for i, nd in enumerate(nodes):
        x = x0 + i * (box_w + gap)
        add_rect(slide, x, y, box_w, 0.85, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
        add_text(slide, x + 0.05, y + 0.22, box_w - 0.1, 0.4, nd, size=13, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER)
        if i < n - 1:
            add_text(slide, x + box_w - 0.02, y + 0.2, gap + 0.04, 0.45, "→", size=16,
                     color=ACCENT, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, 0.6, 3.75, 12.1, 0.4,
             "Статусы по confidence:  success (≥0.7)  ·  low_confidence (self-correction)  ·  failed",
             size=14, color=GRAY, align=PP_ALIGN.CENTER)
    add_text(slide, 0.6, 4.35, 12.1, 0.4, "Что делает каждый узел", size=16, color=WHITE, bold=True)
    add_table(slide, [
        ["Узел", "Что делает"],
        ["Classifier", "тип запроса (lookup, aggregate, delta, cross_sheet…) и домен (prices/metrics)"],
        ["Disambiguation", "уточняет вопрос, если нужно (interrupt или авто-разрешение)"],
        ["Planner", "текстовый план действий"],
        ["CodeGen", "генерация SQL + детерминированные правки + валидация"],
        ["Executor", "выполняет read-only SQL, при пустом результате — fallback-SQL"],
        ["Verifier", "LLM-проверка корректности (до 3 попыток + детерминированный fallback)"],
        ["Answer", "финальный естественно-языковой ответ"],
    ], 0.6, 4.8, 12.1, [2.2, 9.9], row_height=0.3, body_size=11.5, header_size=12)


# ---------------------------------------------------------------------------
# СЛАЙД 18 — Узлы агента (детально)
# ---------------------------------------------------------------------------
def slide_nodes():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "LLM-агент", "Узлы агента — детали", next_page())
    add_table(slide, [
        ["Узел", "Ключевые детали"],
        ["Classifier", "типы: lookup, aggregate, cross_sheet, delta, sum_by_supplier, find_period, unknown; домен: prices/metrics/generic; structured output ClassifierResult"],
        ["Disambiguation", "DisambiguationResult; ветвление через interrupt() (ожидание ответа) либо авто-разрешение"],
        ["Planner", "текстовый план действий (PlannerResult)"],
        ["CodeGen", "LLM-генерация или детерминированный sql_compiler; правки: «все виды меди» → ILIKE 'Лом меди%'; 'Сплав-21' → '%сплав21%'; is_blank → 0/1; validate_sql"],
        ["Executor", "read-only SELECT, statement_timeout; при ошибке — sql_error/retry_reason; серия fallback-SQL при пустом результате"],
        ["Verifier", "LLM-проверка SQL+результата (JSON); до 3 попыток; извлечение JSON-подстроки; детерминированный fallback с confidence 0.75"],
        ["Answer", "финальный естественно-языковой ответ"],
    ], 0.6, 1.95, 12.1, [1.7, 10.4], row_height=0.62, body_size=11.5, header_size=12)


# ---------------------------------------------------------------------------
# СЛАЙД 19 — Безопасная генерация SQL
# ---------------------------------------------------------------------------
def slide_sql():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "LLM-агент", "Безопасная генерация SQL", next_page())
    add_text(slide, 0.6, 1.9, 12.1, 0.4, "Детерминированные правки в CodeGen", size=16,
             color=WHITE, bold=True)
    fixes = [
        ("«Все виды меди»", "→ префиксный фильтр item_name ILIKE 'Лом меди%'"),
        ("Нормализация поставщиков", "→ 'Сплав-21' → '%сплав21%'"),
        ("Булевы поля is_blank", "→ целые 0/1"),
    ]
    for i, (t, b) in enumerate(fixes):
        x = 0.6 + i * 4.15
        add_card(slide, x, 2.35, 3.9, 1.15, title=t, body=b, title_size=14, body_size=12)
    add_text(slide, 0.6, 3.75, 12.1, 0.4, "Валидация перед выполнением", size=16,
             color=WHITE, bold=True)
    checks = [
        ("✓", "Только SELECT (whitelist таблиц mart.*)", GREEN),
        ("✕", "Blacklist: INSERT / UPDATE / DELETE / DROP / ALTER", RED),
        ("✓", "Баланс скобок и кавычек (детекция обрезанного SQL)", GREEN),
        ("⏱", "statement_timeout — 30 сек", BLUE),
    ]
    for i, (mark, t, color) in enumerate(checks):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 4.2 + row * 0.75
        add_rect(slide, x, y, 5.9, 0.6, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
        add_text(slide, x + 0.2, y + 0.1, 0.5, 0.4, mark, size=16, color=color, bold=True)
        add_text(slide, x + 0.75, y + 0.12, 5.0, 0.4, t, size=13, color=WHITE)
    add_rect(slide, 0.6, 5.85, 12.1, 0.85, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_paras(slide, 0.9, 6.0, 11.5, 0.6, [
        {"runs": [("sql_compiler.py — ", 13, ACCENT_LIGHT, True),
                  ("альтернатива LLM: компилирует структурированную спеку в безопасный SELECT напрямую, без модели.", 13, GRAY, False)],
         "line_spacing": 1.1},
    ])


# ---------------------------------------------------------------------------
# СЛАЙД 20 — Entity Resolution
# ---------------------------------------------------------------------------
def slide_entity():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "LLM-агент", "Entity Resolution", next_page())
    add_text(slide, 0.6, 1.9, 12.1, 0.4,
             "Сопоставление упомянутых в вопросе сущностей с реальными", size=16, color=GRAY)
    cards = [
        ("Справочники", "item_name, supplier, sheet_period — каталог реальных значений из БД"),
        ("Fuzzy-match", "rapidfuzz + триграммный поиск PostgreSQL (pg_trgm)"),
        ("BM25-индекс", "data/bm25_index.pkl — выбор релевантных листов (top_k)"),
        ("Кэш", "query_cache — кэш результатов разрешения сущностей"),
    ]
    for i, (t, b) in enumerate(cards):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 2.5 + row * 1.5
        add_card(slide, x, y, 5.9, 1.3, title=t, body=b, title_size=15, body_size=12.5)
    add_rect(slide, 0.6, 5.7, 12.1, 1.0, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_paras(slide, 0.9, 5.85, 11.5, 0.7, [
        {"runs": [("Пример: ", 14, WHITE, True),
                  ("«Средняя цена лома меди у Сплав-21 в январе?»", 14, ACCENT_LIGHT, True),
                  (" → подставляются реальные значения-кандидаты из БД — меньше галлюцинаций названий.", 14, GRAY, False)],
         "line_spacing": 1.15},
    ])


# ---------------------------------------------------------------------------
# СЛАЙД 21 — LLM-клиент и устойчивость
# ---------------------------------------------------------------------------
def slide_llm():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "LLM-агент", "LLM-клиент и устойчивость", next_page())
    add_text(slide, 0.6, 1.9, 5.8, 0.4, "LLMClient (src/services/llm)", size=16,
             color=WHITE, bold=True)
    add_paras(slide, 0.6, 2.35, 5.8, 1.6, [
        {"runs": [("•  ", 13, ACCENT, True), ("chat()", 13, WHITE, True),
                  (" — обычный запрос, возвращает строку", 13, GRAY, False)], "space_after": 6},
        {"runs": [("•  ", 13, ACCENT, True), ("chat_stream()", 13, WHITE, True),
                  (" — стриминг токенов", 13, GRAY, False)], "space_after": 6},
        {"runs": [("•  ", 13, ACCENT, True), ("Совместим с любым OpenAI-подобным API", 13, GRAY, False)]},
    ])
    add_text(slide, 0.6, 4.0, 5.8, 0.4, "Structured output", size=16, color=WHITE, bold=True)
    add_paras(slide, 0.6, 4.45, 5.8, 1.6, [
        {"runs": [("•  ", 13, ACCENT, True),
                  ("get_structured_llm(schema)", 13, WHITE, True),
                  (" через with_structured_output(json_mode)", 13, GRAY, False)], "space_after": 6},
        {"runs": [("•  ", 13, ACCENT, True),
                  ("автопарсинг в валидированный Pydantic-объект", 13, GRAY, False)], "space_after": 6},
        {"runs": [("•  ", 13, ACCENT, True),
                  ("кэш Runnable по схеме", 13, GRAY, False)]},
    ])
    # правая колонка — retry
    add_text(slide, 6.9, 1.9, 5.8, 0.4, "Retry-логика (_try_with_retries)", size=16,
             color=WHITE, bold=True)
    add_rect(slide, 6.9, 2.35, 5.8, 3.7, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
    add_paras(slide, 7.15, 2.6, 5.3, 3.3, [
        {"runs": [("Повтор до MAX_RETRIES раз при:", 14, WHITE, True)], "space_after": 8},
        {"runs": [("•  ", 13, ACCENT, True), ("RateLimitError / APITimeoutError", 13, GRAY, False)],
         "space_after": 6},
        {"runs": [("•  ", 13, ACCENT, True),
                  ("пустом ответе модели (message.content = None)", 13, GRAY, False)],
         "space_after": 10},
        {"runs": [("Пустой ответ трактуется как сбой, а не валидный результат — ключевая защита от "
                   "нестабильных моделей (например, DeepSeek-V4-Flash иногда отдаёт пустой контент).",
                   12.5, GRAY, False)], "line_spacing": 1.15},
    ])
    add_rect(slide, 0.6, 6.15, 12.1, 0.7, fill=ACCENT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, 0.9, 6.3, 11.5, 0.4,
             "Модель конфигурируется через LLM_BASE_URL · LLM_API_KEY · LLM_MODEL_PRIMARY",
             size=14, color=WHITE, bold=True, align=PP_ALIGN.CENTER)


# ---------------------------------------------------------------------------
# СЛАЙД 22 — Разделитель: Интерфейс и наблюдаемость
# ---------------------------------------------------------------------------
def slide_div_ui():
    add_section_divider("05", "Интерфейс и наблюдаемость",
                        "Frontend-приложение, метрики Prometheus/Grafana и защита системы",
                        next_page())


# ---------------------------------------------------------------------------
# СЛАЙД 23 — Frontend
# ---------------------------------------------------------------------------
def slide_frontend():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Интерфейс и наблюдаемость", "Frontend (React + TypeScript)", next_page())
    add_table(slide, [
        ["Страница", "Возможности"],
        ["Чат", "вопросы к агенту, прогресс шагов, SQL-блок, таблица/график результата, источники"],
        ["Файлы", "загрузка Excel, статусы обработки, просмотр листов и структуры"],
        ["Дашборд", "общая панель состояния"],
        ["Метрики", "Prometheus-метрики системы"],
        ["Трейсы", "просмотр выполнения графа агента по шагам"],
    ], 0.6, 1.95, 12.1, [2.0, 10.1], row_height=0.5, body_size=12.5, header_size=13)
    add_text(slide, 0.6, 5.15, 12.1, 0.4, "Ключевые компоненты", size=16, color=WHITE, bold=True)
    add_rect(slide, 0.6, 5.6, 12.1, 1.0, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_paras(slide, 0.9, 5.75, 11.5, 0.7, [
        {"runs": [("AgentProgress · ChatMessage · ResultChart (Chart.js) · ResultTable · SourcesModal · "
                   "SqlBlock · TypingIndicator · SheetViewer · FileUpload", 13, GRAY, False)],
         "line_spacing": 1.2},
    ])


# ---------------------------------------------------------------------------
# СЛАЙД 24 — Наблюдаемость
# ---------------------------------------------------------------------------
def slide_monitoring():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Интерфейс и наблюдаемость", "Наблюдаемость", next_page())
    cards = [
        ("Prometheus", "/metrics",
         "RPS и латентность /ask · per-node latency графа · доля failed/low_confidence · token usage LLM"),
        ("query_logs", "журнал запросов",
         "Latency по узлам · тексты ошибок · полные трейсы"),
        ("Grafana", "порт 3001",
         "визуализация, подключена через provisioning"),
        ("Логи", "loguru",
         "собираются в Docker Compose"),
    ]
    for i, (t, sub, b) in enumerate(cards):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 1.95 + row * 2.0
        add_rect(slide, x, y, 5.9, 1.8, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
        add_text(slide, x + 0.25, y + 0.2, 5.4, 0.4, t, size=17, color=WHITE, bold=True)
        add_text(slide, x + 0.25, y + 0.6, 5.4, 0.35, sub, size=12, color=ACCENT_LIGHT, bold=True)
        add_text(slide, x + 0.25, y + 0.95, 5.4, 0.75, b, size=12, color=GRAY, line_spacing=1.15)


# ---------------------------------------------------------------------------
# СЛАЙД 25 — Безопасность и защита
# ---------------------------------------------------------------------------
def slide_security():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Интерфейс и наблюдаемость", "Безопасность и защита", next_page())
    items = [
        ("API-key auth", "заголовок X-API-Key для /files/* и /ask/*; в dev — отключена"),
        ("Rate limiting", "slowapi: RATE_LIMIT_ASK = 30/min, RATE_LIMIT_UPLOAD = 10/min"),
        ("Read-only SQL", "агент физически не может изменить данные"),
        ("Секреты", "только через .env; рекомендуется secrets-менеджер (Vault)"),
        ("Устойчивость LLM", "ретраи при rate-limit, таймаутах и пустом ответе модели"),
        ("Structured output", "Pydantic для классификатора и планировщика"),
    ]
    for i, (t, b) in enumerate(items):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 1.95 + row * 1.55
        add_card(slide, x, y, 5.9, 1.35, title=t, body=b, title_size=15, body_size=12.5)


# ---------------------------------------------------------------------------
# СЛАЙД 26 — Разделитель: Качество
# ---------------------------------------------------------------------------
def slide_div_qa():
    add_section_divider("06", "Качество",
                        "Тесты, golden-датасет для регрессионного контроля и CI/CD",
                        next_page())


# ---------------------------------------------------------------------------
# СЛАЙД 27 — Качество: тесты
# ---------------------------------------------------------------------------
def slide_tests():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Качество", "Качество: тесты", next_page())
    add_table(slide, [
        ["Тест", "Что проверяет"],
        ["test_sql_compiler.py", "безопасный компилятор SQL"],
        ["test_normalizer_dimension.py", "нормализация измерений"],
        ["test_classifier_domain.py", "классификатор доменов"],
        ["test_parser_header_detection.py", "определение шапки Excel"],
        ["test_sheet_kind_detector_domain.py", "детектор типа листа (prices/matrix/generic)"],
        ["test_golden_dataset.py", "golden-датасет — эталонные вопросы (маркер golden)"],
        ["tests/integration/", "интеграционные тесты с PostgreSQL (маркер integration)"],
    ], 0.6, 1.95, 12.1, [4.4, 7.7], row_height=0.42, body_size=12, header_size=13)
    add_rect(slide, 0.6, 5.35, 12.1, 1.3, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_paras(slide, 0.9, 5.55, 11.5, 1.0, [
        {"runs": [("pytest tests/", 13, ACCENT_LIGHT, True),
                  ("            # юнит-тесты (без LLM)", 13, GRAY, False)], "space_after": 6},
        {"runs": [("pytest -m golden tests/", 13, ACCENT_LIGHT, True),
                  ("  # интеграционные golden-тесты (LLM + данные)", 13, GRAY, False)], "space_after": 6},
        {"runs": [("Golden-датасет прогоняется в CI при каждом изменении промптов / схемы / нормализации.",
                   12.5, GRAY, False)]},
    ])


# ---------------------------------------------------------------------------
# СЛАЙД 28 — Golden dataset и CI/CD
# ---------------------------------------------------------------------------
def slide_golden():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Качество", "Golden dataset и CI/CD", next_page())
    add_text(slide, 0.6, 1.9, 5.8, 0.4, "Golden dataset", size=16, color=WHITE, bold=True)
    add_paras(slide, 0.6, 2.35, 5.8, 2.6, [
        {"runs": [("•  ", 13, ACCENT, True),
                  ("tests/golden_questions.json — 30 эталонных вопросов (g001–g030)", 13, GRAY, False)],
         "space_after": 6},
        {"runs": [("•  ", 13, ACCENT, True),
                  ("ожидаемые SQL-сигнатуры (expected_sql_hint)", 13, GRAY, False)], "space_after": 6},
        {"runs": [("•  ", 13, ACCENT, True),
                  ("типы результата (expected_result_type)", 13, GRAY, False)], "space_after": 6},
        {"runs": [("•  ", 13, ACCENT, True),
                  ("прогон через агента (marker golden)", 13, GRAY, False)], "space_after": 6},
        {"runs": [("•  ", 13, ACCENT, True),
                  ("отчёт по точности: scripts/run_golden_report.py", 13, GRAY, False)]},
    ])
    add_text(slide, 6.9, 1.9, 5.8, 0.4, "CI (ci.yml)", size=16, color=WHITE, bold=True)
    add_rect(slide, 6.9, 2.35, 5.8, 2.6, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_paras(slide, 7.15, 2.6, 5.3, 2.2, [
        {"runs": [("Триггер: push в main/master или pull_request", 13, GRAY, False)], "space_after": 8},
        {"runs": [("•  ", 13, ACCENT, True),
                  ("unit: pytest -m 'not golden and not integration' (Python 3.12, без БД)", 12.5, GRAY, False)],
         "space_after": 6},
        {"runs": [("•  ", 13, ACCENT, True),
                  ("integration: pytest tests/integration (postgres:16)", 12.5, GRAY, False)],
         "space_after": 6},
        {"runs": [("Golden-прогон в CI не запускается — только локально.", 12.5, GRAY, False)]},
    ])
    add_rect(slide, 0.6, 5.35, 12.1, 1.3, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_paras(slide, 0.9, 5.55, 11.5, 1.0, [
        {"runs": [("Подготовка golden-прогона:", 13, WHITE, True)], "space_after": 6},
        {"runs": [("docker compose up -d  ·  alembic upgrade head  ·  "
                   "python scripts/load_demo_data.py --check-mart  ·  "
                   "python scripts/run_golden_report.py --json out/golden_report.json",
                   12.5, ACCENT_LIGHT, False)], "line_spacing": 1.2},
    ])


# ---------------------------------------------------------------------------
# СЛАЙД 29 — Разделитель: Демонстрация и развёртывание
# ---------------------------------------------------------------------------
def slide_div_demo():
    add_section_divider("07", "Демонстрация и развёртывание",
                        "Сценарий демонстрации, Docker Compose и быстрый старт",
                        next_page())


# ---------------------------------------------------------------------------
# СЛАЙД 30 — Демонстрация — сценарий
# ---------------------------------------------------------------------------
def slide_demo():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Демонстрация и развёртывание", "Демонстрация — сценарий", next_page())
    steps = [
        ("Ш1", "Загрузка файла", "Открываем «Файлы» → загружаем xlsx → система парсит, инферит схему, нормализует в витрину"),
        ("Ш2", "Вопрос в чате", "«Покажи среднюю цену лома меди у поставщика Сплав-21 за январь»"),
        ("Ш3", "Наблюдаем агента", "Прогресс шагов: Classifier → Planner → CodeGen → Executor → Verifier → Answer"),
        ("Ш4", "Проверяем прозрачность", "SQL-запрос, таблица/график с результатом, источники (листы и ячейки)"),
        ("Ш5", "Метрики и трейсы", "Latency узлов в Metrics и полный трейс запроса в Trace"),
    ]
    for i, (num, t, b) in enumerate(steps):
        y = 1.95 + i * 0.95
        add_rect(slide, 0.6, y, 0.85, 0.75, fill=ACCENT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.15)
        add_text(slide, 0.6, y + 0.18, 0.85, 0.4, num, size=16, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, 1.7, y + 0.02, 3.0, 0.4, t, size=16, color=WHITE, bold=True)
        add_text(slide, 1.7, y + 0.4, 11.0, 0.4, b, size=12.5, color=GRAY)


# ---------------------------------------------------------------------------
# СЛАЙД 31 — Архитектура развёртывания
# ---------------------------------------------------------------------------
def slide_deploy():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Демонстрация и развёртывание", "Архитектура развёртывания", next_page())
    add_table(slide, [
        ["Сервис", "Порт", "Назначение"],
        ["postgres", "5432", "PostgreSQL 16 (+ pg_trgm)"],
        ["service", "8000", "FastAPI-приложение (Swagger /docs)"],
        ["frontend", "8080", "React + Nginx"],
        ["prometheus", "9090", "сбор метрик"],
        ["grafana", "3001", "дашборды (admin/admin)"],
    ], 0.6, 1.95, 12.1, [2.6, 1.6, 7.9], row_height=0.5, body_size=13, header_size=13)
    add_text(slide, 0.6, 5.15, 12.1, 0.4, "Запуск", size=16, color=WHITE, bold=True)
    add_rect(slide, 0.6, 5.6, 12.1, 1.1, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_paras(slide, 0.9, 5.75, 11.5, 0.85, [
        {"runs": [("cp .env.example .env        # заполнить LLM_* и POSTGRES_*", 13, ACCENT_LIGHT, True)],
         "space_after": 4},
        {"runs": [("docker compose up --build -d", 13, ACCENT_LIGHT, True)], "space_after": 4},
        {"runs": [("docker compose exec service alembic upgrade head   # → http://localhost:8080",
                   13, ACCENT_LIGHT, True)]},
    ])


# ---------------------------------------------------------------------------
# СЛАЙД 32 — Быстрый старт
# ---------------------------------------------------------------------------
def slide_quickstart():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Демонстрация и развёртывание", "Быстрый старт", next_page())
    steps = [
        ("1", "Конфигурация", "cp .env.example .env → заполнить LLM_* и POSTGRES_*"),
        ("2", "Запуск", "docker compose up --build -d"),
        ("3", "Миграции", "docker compose exec service alembic upgrade head"),
        ("4", "Данные", "загрузить Excel через страницу «Файлы»"),
        ("5", "Вопросы", "задавать вопросы в «Чате»"),
    ]
    for i, (num, t, b) in enumerate(steps):
        y = 1.95 + i * 0.85
        add_rect(slide, 0.6, y, 0.7, 0.65, fill=BLUE, shape=MSO_SHAPE.OVAL)
        add_text(slide, 0.6, y + 0.1, 0.7, 0.45, num, size=16, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, 1.55, y + 0.02, 2.4, 0.4, t, size=15, color=WHITE, bold=True)
        add_text(slide, 1.55, y + 0.38, 11.2, 0.4, b, size=12.5, color=GRAY)
    add_rect(slide, 0.6, 6.3, 12.1, 0.7, fill=ACCENT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, 0.9, 6.45, 11.5, 0.4,
             "Backend: :8000/docs (Swagger)  ·  Frontend: :8080  ·  Prometheus: :9090  ·  Grafana: :3001",
             size=14, color=WHITE, bold=True, align=PP_ALIGN.CENTER)


# ---------------------------------------------------------------------------
# СЛАЙД 33 — Разделитель: Итоги
# ---------------------------------------------------------------------------
def slide_div_results():
    add_section_divider("08", "Итоги",
                        "Что сделано, ключевые принципы и перспективы развития",
                        next_page())


# ---------------------------------------------------------------------------
# СЛАЙД 34 — Итоги и перспективы
# ---------------------------------------------------------------------------
def slide_results():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Итоги", "Итоги и перспективы", next_page())
    add_text(slide, 0.6, 1.9, 5.8, 0.4, "Что сделано", size=16, color=WHITE, bold=True)
    done = [
        "Асинхронный ingestion Excel → нормализованная витрина данных",
        "LangGraph-агент «вопрос → SQL → ответ» с полным трейсом",
        "Безопасная генерация SQL (whitelist + blacklist + валидация)",
        "Entity Resolution для точного сопоставления сущностей",
        "Современный React-интерфейс (чат, файлы, метрики, трейсы)",
        "Наблюдаемость: Prometheus + Grafana + журнал запросов",
        "Golden-датасет и тесты для контроля качества",
    ]
    paras = []
    for it in done:
        paras.append({"runs": [("✓  ", 13, GREEN, True), (it, 13, GRAY, False)],
                      "space_after": 7, "line_spacing": 1.05})
    add_paras(slide, 0.6, 2.35, 5.9, 4.3, paras)
    add_text(slide, 6.9, 1.9, 5.8, 0.4, "Ключевые принципы", size=16, color=WHITE, bold=True)
    add_rect(slide, 6.9, 2.35, 5.8, 1.5, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_paras(slide, 7.15, 2.6, 5.3, 1.1, [
        {"runs": [("Нормализация вместо векторного поиска", 14, WHITE, True)], "space_after": 6},
        {"runs": [("Детерминизм вместо «магии» LLM", 14, WHITE, True)], "space_after": 6},
        {"runs": [("Прозрачность каждого ответа", 14, WHITE, True)]},
    ])
    add_text(slide, 6.9, 4.1, 5.8, 0.4, "Перспективы развития", size=16, color=WHITE, bold=True)
    future = [
        "Расширение типов вопросов и golden-датасета",
        "Поддержка новых форматов листов (Schema Inference готов)",
        "Secrets-менеджер (Vault) для прод-контура",
        "Интеграция с корпоративной авторизацией (SSO)",
        "Автоматические алерты в Grafana по качеству ответов",
        "Мобильный клиент и экспорт отчётов",
    ]
    paras = []
    for it in future:
        paras.append({"runs": [("•  ", 13, ACCENT, True), (it, 13, GRAY, False)],
                      "space_after": 7, "line_spacing": 1.05})
    add_paras(slide, 6.9, 4.55, 5.9, 2.2, paras)


# ---------------------------------------------------------------------------
# СЛАЙД 35 — Спасибо за внимание
# ---------------------------------------------------------------------------
def slide_thanks():
    slide = _new_slide()
    set_bg(slide, BG_DARK)
    add_rect(slide, 0, 0, 0.18, H_IN, fill=ACCENT)
    add_rect(slide, 0.6, 2.5, 0.5, 0.07, fill=ACCENT)
    add_text(slide, 0.6, 2.65, 9, 0.4, "СПАСИБО ЗА ВНИМАНИЕ", size=14, color=ACCENT_LIGHT, bold=True)
    add_text(slide, 0.6, 3.1, 12, 1.0, "EVRAZ Agent", size=52, color=WHITE, bold=True)
    add_text(slide, 0.6, 4.15, 11.5, 0.5,
             "AI-агент для интеллектуальной работы с Excel-файлами", size=18, color=GRAY)
    add_text(slide, 0.6, 5.0, 11.5, 0.5, "Вопросы?", size=20, color=ACCENT_LIGHT, bold=True)
    add_text(slide, 0.6, 6.0, 11.5, 0.4,
             "Подробности:  README.md  ·  PROJECT.md  ·  INSTRUCTIONS.md", size=13, color=GRAY)
    add_footer(slide, next_page())


# ---------------------------------------------------------------------------
# ДИАГРАММА: Архитектура системы (полная)
# ---------------------------------------------------------------------------
def slide_arch_diagram():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Решение и архитектура", "Архитектура системы — диаграмма", next_page())
    # Пользователь
    add_rect(slide, 5.7, 1.7, 1.9, 0.45, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.2)
    add_text(slide, 5.7, 1.78, 1.9, 0.3, "Пользователь", size=12, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_arrow(slide, 6.65, 2.15, 6.65, 2.4)
    # Frontend
    add_rect(slide, 4.4, 2.4, 4.5, 0.6, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 4.5, 2.47, 4.3, 0.3, "Frontend — React + Vite (Nginx)", size=12,
             color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, 4.5, 2.75, 4.3, 0.2, "Чат · Файлы · Дашборд · Метрики · Трейс",
             size=9, color=GRAY, align=PP_ALIGN.CENTER)
    add_arrow(slide, 6.65, 3.0, 6.65, 3.2)
    add_text(slide, 6.8, 3.0, 1.4, 0.2, "REST/HTTP", size=8, color=GRAY)
    # Backend box
    add_rect(slide, 0.5, 3.2, 8.0, 3.1, fill=BG_DARK, line=BLUE, line_w=1.5,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
    add_text(slide, 0.7, 3.28, 7.6, 0.3, "Backend — FastAPI (uvicorn, :8000)", size=12,
             color=ACCENT_LIGHT, bold=True)
    nodes = [
        ("API роутеры", "/files, /ask, /trace", 0.8, 3.65),
        ("Ingestion Queue", "async worker", 2.7, 3.65),
        ("LangGraph агент", "classifier → … → answer", 4.6, 3.65),
        ("LLMClient", "OpenAI-совместимый API", 6.5, 3.65),
        ("Excel ingestion", "парсер → repository → mart", 0.8, 4.5),
        ("Entity Resolution", "rapidfuzz + BM25", 2.7, 4.5),
        ("Query Cache", "вопрос → SQL → результат", 4.6, 4.5),
        ("Prometheus /metrics", "метрики приложения", 6.5, 4.5),
    ]
    for title, sub, x, y in nodes:
        add_rect(slide, x, y, 1.7, 0.65, fill=BG, line=CARD_BORDER,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
        add_text(slide, x + 0.08, y + 0.08, 1.54, 0.3, title, size=9.5, color=WHITE,
                 bold=True, align=PP_ALIGN.CENTER)
        add_text(slide, x + 0.08, y + 0.36, 1.54, 0.25, sub, size=7.5, color=GRAY,
                 align=PP_ALIGN.CENTER)
    # LLM provider
    add_rect(slide, 8.9, 3.2, 3.9, 1.1, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_text(slide, 9.0, 3.35, 3.7, 0.3, "LLM-провайдер", size=12, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, 9.0, 3.7, 3.7, 0.4, "DeepSeek / любая OpenAI-совместимая модель",
             size=9, color=GRAY, align=PP_ALIGN.CENTER)
    # PostgreSQL
    add_rect(slide, 0.5, 6.5, 5.9, 0.55, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 0.7, 6.56, 5.5, 0.28, "PostgreSQL 16", size=11, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, 0.7, 6.8, 5.5, 0.2, "public: files, sheets, cells · mart: price_facts, metrics",
             size=8, color=GRAY, align=PP_ALIGN.CENTER)
    # Monitoring
    add_rect(slide, 6.9, 6.5, 5.9, 0.55, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 7.1, 6.56, 5.5, 0.28, "Мониторинг", size=11, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, 7.1, 6.8, 5.5, 0.2, "Prometheus :9090 · Grafana :3001", size=8,
             color=GRAY, align=PP_ALIGN.CENTER)
    # стрелки внутри backend
    add_arrow(slide, 2.5, 3.97, 2.7, 3.97)                       # API -> Queue
    add_text(slide, 2.5, 3.72, 1.6, 0.2, "POST /files/upload", size=7.5, color=GRAY)
    add_arrow(slide, 3.55, 4.3, 3.55, 4.5)                       # Queue -> Ingestion
    add_arrow(slide, 2.5, 3.97, 4.6, 3.97)                       # API -> Agent
    add_text(slide, 3.0, 3.72, 1.6, 0.2, "POST /ask", size=7.5, color=GRAY)
    add_arrow(slide, 6.3, 3.97, 8.2, 3.97)                       # Agent -> LLMClient
    add_arrow(slide, 8.2, 3.97, 8.9, 3.97)                       # LLMClient -> LLM provider
    add_text(slide, 8.2, 3.72, 1.6, 0.2, "chat / structured output", size=7.5, color=GRAY)
    add_arrow(slide, 5.45, 4.3, 5.45, 4.5)                       # Agent -> Cache
    add_arrow(slide, 4.6, 4.3, 3.55, 4.5)                        # Agent -> Entity Res
    # стрелки вниз
    add_arrow(slide, 1.65, 5.15, 1.65, 6.5)                      # Ingestion -> PostgreSQL
    add_text(slide, 1.75, 5.6, 1.8, 0.2, "RAW + нормализация", size=7.5, color=GRAY)
    add_arrow(slide, 5.45, 5.15, 4.0, 6.5)                       # Cache/Agent -> PostgreSQL
    add_text(slide, 5.0, 5.6, 1.8, 0.2, "безопасный SELECT", size=7.5, color=GRAY)
    add_arrow(slide, 7.35, 5.15, 7.35, 6.5)                      # Metrics -> Monitoring
    add_text(slide, 7.45, 5.6, 1.4, 0.2, "/metrics", size=7.5, color=GRAY)


# ---------------------------------------------------------------------------
# ДИАГРАММА: Граф LLM-агента
# ---------------------------------------------------------------------------
def slide_agent_diagram():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "LLM-агент", "Граф LLM-агента — диаграмма", next_page())
    x = 0.8
    w = 3.6
    nodes = [
        ("Вопрос пользователя (POST /ask)", 1.7, True),
        ("classifier — тип запроса + домен", 2.3, False),
        ("disambiguation — нужно ли уточнение", 2.9, False),
        ("planner — план действий", 3.5, False),
        ("codegen — генерация безопасного SQL", 4.1, False),
        ("executor — выполнение SELECT (read-only)", 4.7, False),
        ("verifier — LLM-проверка SQL + результата", 5.3, False),
        ("answer — формирование ответа", 5.9, False),
        ("END", 6.5, True),
    ]
    for text, y, stadium in nodes:
        add_rect(slide, x, y, w, 0.45, fill=BG_DARK, line=CARD_BORDER,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5 if stadium else 0.12)
        add_text(slide, x + 0.1, y + 0.08, w - 0.2, 0.3, text, size=10.5, color=WHITE,
                 bold=stadium, align=PP_ALIGN.CENTER)
    # вертикальные стрелки
    for y in (2.15, 2.75, 3.35, 3.95, 4.55, 5.15, 5.75, 6.35):
        add_arrow(slide, x + w / 2, y, x + w / 2, y + 0.15)
    # Failed box
    fx = 6.5
    add_rect(slide, fx, 2.3, 2.4, 0.45, fill=BG_DARK, line=RED, line_w=1.2,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, fx + 0.1, 2.38, 2.2, 0.3, "failed", size=11, color=RED, bold=True,
             align=PP_ALIGN.CENTER)
    # End box (right)
    add_rect(slide, fx, 6.5, 2.4, 0.4, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
    add_text(slide, fx + 0.1, 6.56, 2.2, 0.28, "END", size=10, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    # Classifier -> Failed
    add_arrow(slide, 4.4, 2.52, fx, 2.52, color=RED, width=1.2)
    add_text(slide, 4.5, 2.3, 1.9, 0.2, "query_type = None", size=7.5, color=GRAY)
    # CodeGen -> Failed
    add_arrow(slide, 4.4, 4.32, fx, 2.75, color=RED, width=1.2)
    add_text(slide, 4.5, 3.4, 1.9, 0.2, "ретраи = 3", size=7.5, color=GRAY)
    # Executor -> Failed
    add_arrow(slide, 4.4, 4.92, fx, 2.75, color=RED, width=1.2)
    # Answer -> End
    add_arrow(slide, 4.4, 6.12, fx, 6.5)
    # Failed -> End
    add_arrow(slide, 7.7, 2.75, 7.7, 6.5, color=RED, width=1.2)
    # петли (справа)
    add_elbow(slide, 4.4, 4.32, 5.2, 4.32, color=BLUE, width=1.2)   # codegen self-loop
    add_text(slide, 4.5, 4.1, 1.6, 0.2, "ретраи < 3", size=7.5, color=BLUE)
    add_elbow(slide, 4.4, 4.92, 5.2, 4.32, color=BLUE, width=1.2)   # executor -> codegen
    add_text(slide, 4.5, 4.55, 1.6, 0.2, "sql_error, ретраи < 3", size=7.5, color=BLUE)
    add_elbow(slide, 4.4, 5.52, 5.2, 4.32, color=BLUE, width=1.2)   # verifier -> codegen
    add_text(slide, 4.5, 5.15, 1.6, 0.2, "needs_retry, ретраи < 3", size=7.5, color=BLUE)


# ---------------------------------------------------------------------------
# ДИАГРАММА: Пайплайн Excel-инжеста
# ---------------------------------------------------------------------------
def slide_ingestion_diagram():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Обработка данных", "Пайплайн Excel-инжеста — диаграмма", next_page())
    # Start
    add_rect(slide, 0.8, 1.7, 2.6, 0.5, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
    add_text(slide, 0.9, 1.78, 2.4, 0.3, "POST /files/upload", size=11, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_arrow(slide, 3.4, 1.95, 4.0, 1.95)
    # Validation (diamond)
    add_rect(slide, 4.0, 1.6, 2.8, 0.7, fill=BG_DARK, line=ACCENT, line_w=1.2,
             shape=MSO_SHAPE.DIAMOND)
    add_text(slide, 4.1, 1.78, 2.6, 0.4, "Валидация\n.xlsx/.xls, max 50 МБ", size=9,
             color=WHITE, align=PP_ALIGN.CENTER)
    # no -> error
    add_arrow(slide, 6.8, 1.95, 7.4, 1.95, color=RED, width=1.2)
    add_text(slide, 6.85, 1.72, 1.0, 0.2, "нет", size=8, color=RED)
    add_rect(slide, 7.4, 1.7, 2.4, 0.5, fill=BG_DARK, line=RED, line_w=1.2,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, 7.5, 1.78, 2.2, 0.3, "400 ValidationError", size=10, color=RED, bold=True,
             align=PP_ALIGN.CENTER)
    # yes -> temp
    add_arrow(slide, 5.4, 2.3, 5.4, 2.6)
    add_text(slide, 5.5, 2.32, 0.8, 0.2, "да", size=8, color=GREEN)
    add_rect(slide, 4.0, 2.6, 2.8, 0.5, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, 4.1, 2.68, 2.6, 0.3, "Запись во временный файл", size=10, color=WHITE,
             align=PP_ALIGN.CENTER)
    add_arrow(slide, 5.4, 3.1, 5.4, 3.4)
    add_rect(slide, 4.0, 3.4, 2.8, 0.5, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, 4.1, 3.48, 2.6, 0.3, "IngestionQueue (async worker)", size=10, color=WHITE,
             align=PP_ALIGN.CENTER)
    add_arrow(slide, 5.4, 3.9, 5.4, 4.2)
    # Parse subgraph
    add_rect(slide, 0.5, 4.2, 9.8, 1.9, fill=BG_DARK, line=BLUE, line_w=1.2,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
    add_text(slide, 0.7, 4.28, 9.4, 0.3, "Парсинг (src/core/excel)", size=11,
             color=ACCENT_LIGHT, bold=True)
    add_rect(slide, 0.8, 4.7, 2.2, 0.55, fill=BG, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 0.9, 4.78, 2.0, 0.4, "ExcelParser\nunmerge, detect header rows", size=8.5,
             color=WHITE, align=PP_ALIGN.CENTER)
    add_arrow(slide, 3.0, 4.97, 3.4, 4.97)
    add_rect(slide, 3.4, 4.7, 2.2, 0.55, fill=BG, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 3.5, 4.78, 2.0, 0.4, "Pydantic ParsedFile\nsheets / headers / cells", size=8.5,
             color=WHITE, align=PP_ALIGN.CENTER)
    subs = [
        ("ExcelNormalizer", 0.8, 5.45),
        ("sheet_kind_detector", 2.7, 5.45),
        ("TableStructurer", 4.6, 5.45),
        ("comment_extractor", 6.5, 5.45),
    ]
    for t, sx, sy in subs:
        add_rect(slide, sx, sy, 1.7, 0.5, fill=BG, line=CARD_BORDER,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
        add_text(slide, sx + 0.08, sy + 0.1, 1.54, 0.3, t, size=8.5, color=WHITE,
                 align=PP_ALIGN.CENTER)
        add_arrow(slide, 4.5, 5.25, sx + 0.85, 5.45, color=GRAY, width=1.0)
    # Repository
    add_rect(slide, 0.8, 6.4, 2.6, 0.5, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, 0.9, 6.48, 2.4, 0.3, "SQLAlchemyExcelRepository", size=9, color=WHITE,
             align=PP_ALIGN.CENTER)
    add_arrow(slide, 1.65, 5.95, 1.65, 6.4)
    # RAW
    add_rect(slide, 4.0, 6.4, 2.8, 0.5, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, 4.1, 6.48, 2.6, 0.3, "RAW: files, sheets, cells…", size=9, color=WHITE,
             align=PP_ALIGN.CENTER)
    add_arrow(slide, 3.4, 6.65, 4.0, 6.65)
    # Mart
    add_rect(slide, 7.4, 6.4, 2.8, 0.5, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, 7.5, 6.48, 2.6, 0.3, "normalize_file_to_mart", size=9, color=WHITE,
             align=PP_ALIGN.CENTER)
    add_arrow(slide, 6.8, 6.65, 7.4, 6.65)
    # Done
    add_rect(slide, 7.4, 7.0, 2.8, 0.4, fill=ACCENT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
    add_text(slide, 7.5, 7.05, 2.6, 0.3, "File status = processed", size=9, color=WHITE,
             bold=True, align=PP_ALIGN.CENTER)


# ---------------------------------------------------------------------------
# ДИАГРАММА: Схема БД (ER)
# ---------------------------------------------------------------------------
def slide_er_diagram():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Обработка данных", "Схема базы данных — ER-диаграмма", next_page())
    add_entity_box(slide, 0.5, 1.7, 2.7, 1.5, "FILES", [
        "id PK", "filename", "file_hash UK", "status", "uploaded_at",
    ])
    add_entity_box(slide, 0.5, 3.4, 2.7, 1.3, "SHEETS", [
        "id PK", "file_id FK", "original_name", "period", "sheet_kind",
    ])
    add_entity_box(slide, 0.5, 5.0, 2.7, 1.3, "COLUMN_METADATA", [
        "id PK", "sheet_id FK", "col_index", "data_type", "role",
    ])
    add_entity_box(slide, 3.5, 5.0, 2.7, 1.3, "CELLS", [
        "id PK", "sheet_id FK", "row_num", "value_text", "value_number",
    ])
    add_entity_box(slide, 6.5, 5.0, 2.7, 1.3, "EXCEL_COMMENTS", [
        "id PK", "sheet_id FK", "cell_ref", "author", "text",
    ])
    add_entity_box(slide, 3.5, 1.7, 2.7, 1.5, "MART_PRICE_FACTS", [
        "id PK", "file_id FK", "item_name", "supplier", "price_type", "value",
    ])
    add_entity_box(slide, 6.5, 1.7, 2.7, 1.5, "MART_METRICS", [
        "id PK", "file_id FK", "dimension", "metric_type", "value", "is_blank",
    ])
    add_entity_box(slide, 9.5, 1.7, 2.7, 1.3, "QUERY_CACHE", [
        "id PK", "question_hash UK", "sql_query", "result",
    ])
    add_entity_box(slide, 9.5, 3.4, 2.7, 1.3, "QUERY_LOGS", [
        "id PK", "request_id", "question", "sql_query", "trace",
    ])
    add_entity_box(slide, 9.5, 5.0, 2.7, 1.3, "GOLDEN_DATASET", [
        "id PK", "question", "expected_sql", "category",
    ])
    add_entity_box(slide, 3.5, 3.4, 2.7, 1.3, "ENTITY_DICTIONARY", [
        "id PK", "canonical_name UK", "aliases", "category",
    ])
    # связи
    add_arrow(slide, 1.85, 3.2, 1.85, 3.4, color=GRAY, width=1.0)      # FILES -> SHEETS
    add_arrow(slide, 1.85, 4.7, 1.85, 5.0, color=GRAY, width=1.0)      # SHEETS -> COLUMN_METADATA
    add_arrow(slide, 3.5, 5.65, 3.5, 5.0, color=GRAY, width=1.0)       # SHEETS -> CELLS
    add_arrow(slide, 6.5, 5.65, 6.5, 5.0, color=GRAY, width=1.0)       # SHEETS -> EXCEL_COMMENTS
    add_arrow(slide, 3.2, 2.45, 3.5, 2.45, color=GRAY, width=1.0)      # FILES -> MART_PRICE_FACTS
    add_arrow(slide, 6.2, 2.45, 6.5, 2.45, color=GRAY, width=1.0)      # FILES -> MART_METRICS
    add_text(slide, 0.5, 6.4, 12.0, 0.4,
             "Связи: FILES 1—N SHEETS · SHEETS 1—N COLUMN_METADATA/CELLS/EXCEL_COMMENTS · "
             "FILES 1—N MART_PRICE_FACTS/MART_METRICS", size=10, color=GRAY, align=PP_ALIGN.CENTER)


# ---------------------------------------------------------------------------
# ДИАГРАММА: CI/CD
# ---------------------------------------------------------------------------
def slide_cicd_diagram():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Качество", "CI/CD — диаграмма", next_page())
    # Trigger
    add_rect(slide, 0.8, 2.4, 3.6, 0.7, fill=BG_DARK, line=ACCENT, line_w=1.2,
             shape=MSO_SHAPE.HEXAGON)
    add_text(slide, 0.9, 2.55, 3.4, 0.4, "push в main/master\nили pull_request", size=10,
             color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    add_arrow(slide, 4.4, 2.75, 5.0, 2.75)
    # CI box
    add_rect(slide, 5.0, 1.8, 7.3, 3.2, fill=BG_DARK, line=BLUE, line_w=1.2,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
    add_text(slide, 5.2, 1.9, 6.9, 0.3, "ci.yml — CI (unit + integration)", size=12,
             color=ACCENT_LIGHT, bold=True)
    add_rect(slide, 5.3, 2.35, 6.7, 0.9, fill=BG, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_text(slide, 5.5, 2.5, 6.3, 0.6, "unit\npytest -m 'not golden and not integration' · Ubuntu, Python 3.12, без БД",
             size=9.5, color=WHITE, align=PP_ALIGN.CENTER)
    add_arrow(slide, 7.65, 3.25, 7.65, 3.55)
    add_text(slide, 7.75, 3.3, 1.2, 0.2, "needs", size=8, color=GRAY)
    add_rect(slide, 5.3, 3.55, 6.7, 0.9, fill=BG, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_text(slide, 5.5, 3.7, 6.3, 0.6, "integration\npytest tests/integration · service: postgres:16, TEST_POSTGRES_URL",
             size=9.5, color=WHITE, align=PP_ALIGN.CENTER)
    add_rect(slide, 5.0, 5.2, 7.3, 0.6, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 5.2, 5.35, 6.9, 0.3, "Golden-прогон в CI не запускается — только локально",
             size=10, color=GRAY, align=PP_ALIGN.CENTER)


# ---------------------------------------------------------------------------
# ДИАГРАММА: Развёртывание (Docker Compose)
# ---------------------------------------------------------------------------
def slide_deploy_diagram():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Демонстрация и развёртывание", "Развёртывание — диаграмма", next_page())
    # Browser
    add_rect(slide, 5.7, 1.7, 1.9, 0.5, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.15)
    add_text(slide, 5.7, 1.78, 1.9, 0.3, "Браузер пользователя", size=10, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_arrow(slide, 6.65, 2.2, 6.65, 2.5)
    add_text(slide, 6.8, 2.22, 1.6, 0.2, ":8080 или :80", size=8, color=GRAY)
    # Frontend
    add_rect(slide, 5.7, 2.5, 1.9, 0.6, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 5.7, 2.58, 1.9, 0.3, "Nginx :80/:8080", size=10, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, 5.7, 2.85, 1.9, 0.2, "React static build", size=8, color=GRAY,
             align=PP_ALIGN.CENTER)
    add_arrow(slide, 6.65, 3.1, 6.65, 3.4)
    add_text(slide, 6.8, 3.12, 1.6, 0.2, "/api → :8000", size=8, color=GRAY)
    # Backend
    add_rect(slide, 5.7, 3.4, 1.9, 0.6, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 5.7, 3.48, 1.9, 0.3, "service :8000", size=10, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, 5.7, 3.75, 1.9, 0.2, "uvicorn src.main:app", size=8, color=GRAY,
             align=PP_ALIGN.CENTER)
    # Data
    add_rect(slide, 1.6, 4.4, 3.0, 0.9, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_text(slide, 1.7, 4.5, 2.8, 0.3, "postgres:16-alpine :5432", size=10, color=WHITE,
             bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, 1.7, 4.8, 2.8, 0.4, "scripts/init-db →\ndocker-entrypoint-initdb.d", size=8,
             color=GRAY, align=PP_ALIGN.CENTER)
    add_arrow(slide, 6.65, 4.0, 3.1, 4.4)
    add_text(slide, 4.2, 4.05, 1.6, 0.2, ":5432, asyncpg", size=8, color=GRAY)
    # Observability
    add_rect(slide, 8.7, 4.4, 3.0, 0.9, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_text(slide, 8.8, 4.5, 2.8, 0.3, "prometheus :9090", size=10, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, 8.8, 4.8, 2.8, 0.4, "grafana :3001 (admin/admin)\ndatasource provisioning", size=8,
             color=GRAY, align=PP_ALIGN.CENTER)
    add_arrow(slide, 6.65, 4.0, 8.7, 4.4)
    add_text(slide, 7.0, 4.05, 1.6, 0.2, "/metrics :8000", size=8, color=GRAY)
    # LLM API
    add_rect(slide, 5.7, 5.6, 1.9, 0.6, fill=BG_DARK, line=CARD_BORDER,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    add_text(slide, 5.7, 5.68, 1.9, 0.3, "LLM API", size=10, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, 5.7, 5.95, 1.9, 0.2, "OpenAI-совместимый", size=8, color=GRAY,
             align=PP_ALIGN.CENTER)
    add_arrow(slide, 6.65, 4.0, 6.65, 5.6)
    add_text(slide, 6.8, 4.6, 1.6, 0.2, "LLM_BASE_URL", size=8, color=GRAY)
    # Grafana -> Prometheus
    add_arrow(slide, 8.7, 5.3, 8.7, 5.0, color=GRAY, width=1.0)
    add_text(slide, 8.8, 5.05, 1.6, 0.2, "datasource", size=8, color=GRAY)


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------
def build():
    slide_title()
    slide_toc()
    slide_about()
    slide_problem()
    slide_goal()
    slide_div_arch()
    slide_solution()
    slide_architecture()
    slide_arch_diagram()
    slide_stack()
    slide_structure()
    slide_div_data()
    slide_pipeline()
    slide_ingestion_diagram()
    slide_parsing()
    slide_mart()
    slide_db()
    slide_er_diagram()
    slide_div_agent()
    slide_agent()
    slide_agent_diagram()
    slide_nodes()
    slide_sql()
    slide_entity()
    slide_llm()
    slide_div_ui()
    slide_frontend()
    slide_monitoring()
    slide_security()
    slide_div_qa()
    slide_tests()
    slide_golden()
    slide_cicd_diagram()
    slide_div_demo()
    slide_demo()
    slide_deploy()
    slide_deploy_diagram()
    slide_quickstart()
    slide_div_results()
    slide_results()
    slide_thanks()

    out = "data/EVRAZ_Agent_updated.pptx"
    prs.save(out)
    print(f"OK: {len(prs.slides.__iter__.__self__._sldIdLst)} slides -> {out}")


if __name__ == "__main__":
    build()
