# -*- coding: utf-8 -*-
"""Генерация презентации EVRAZ Agent для защиты (версия 20 слайдов).

Ориентирована на аудиторию, не знакомую с программированием:
акцент на проблему, решение, результаты и выгоды для бизнеса;
технические детали сведены к минимуму и объяснены простыми словами.

Создаёт data/EVRAZ_Agent_defense.pptx
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# ---------------------------------------------------------------------------
# Палитра (фирменный стиль EVRAZ: тёмная тема + оранжевый акцент)
# ---------------------------------------------------------------------------
BG = RGBColor(0x1B, 0x1F, 0x24)          # основной фон
BG_DARK = RGBColor(0x26, 0x2C, 0x33)     # фон титула / карточек
ACCENT = RGBColor(0xFF, 0x5A, 0x36)      # оранжевый EVRAZ
ACCENT_LIGHT = RGBColor(0xFF, 0xB1, 0x99)
BLUE = RGBColor(0x1C, 0x72, 0x93)        # синий (метки разделов)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GRAY = RGBColor(0x8A, 0x97, 0xA6)        # вторичный текст на тёмном
TEXT_DARK = RGBColor(0x1B, 0x1F, 0x24)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
RED = RGBColor(0xC6, 0x28, 0x28)
ZEBRA = RGBColor(0xF0, 0xF2, 0xF5)
CARD_BORDER = RGBColor(0x3D, 0x4A, 0x57)

FONT = "Calibri"

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
             title_size=16, body_size=12.5, number_color=ACCENT, body_align=PP_ALIGN.LEFT):
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


def add_kpi(slide, x, y, w, h, number, label, sub=None, number_size=44,
            number_color=ACCENT):
    """Цифра-индикатор (KPI) на карточке.

    Высокая карточка (h > 1.3"): крупная цифра по центру, подпись и пояснение ниже.
    Компактная карточка (h <= 1.3"): цифра слева, подпись справа по вертикали.
    """
    add_rect(slide, x, y, w, h, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    if h <= 1.3:
        # компактная: горизонтальная раскладка
        add_text(slide, x + 0.25, y + 0.12, 2.6, h - 0.24, number, size=30,
                 color=number_color, bold=True, align=PP_ALIGN.LEFT,
                 anchor=MSO_ANCHOR.MIDDLE)
        add_text(slide, x + 2.9, y + 0.15, w - 3.15, h - 0.3, label, size=14,
                 color=WHITE, bold=True, align=PP_ALIGN.LEFT,
                 anchor=MSO_ANCHOR.MIDDLE, line_spacing=1.05)
        if sub:
            add_text(slide, x + 0.25, y + h + 0.06, w - 0.5, 0.3, sub, size=10.5,
                     color=GRAY, align=PP_ALIGN.CENTER, line_spacing=1.05)
        return
    add_text(slide, x + 0.2, y + 0.2, w - 0.4, 0.95, number, size=number_size,
             color=number_color, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, x + 0.2, y + 1.15, w - 0.4, 0.45, label, size=15,
             color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    if sub:
        add_text(slide, x + 0.25, y + 1.62, w - 0.5, h - 1.7, sub, size=11.5,
                 color=GRAY, align=PP_ALIGN.CENTER, line_spacing=1.12)


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


def add_band(slide, x, y, w, h, text, size=15, fill=ACCENT, color=WHITE, align=PP_ALIGN.CENTER):
    """Акцентная плашка с текстом."""
    add_rect(slide, x, y, w, h, fill=fill, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, x + 0.3, y + 0.18, w - 0.6, h - 0.36, text, size=size,
             color=color, bold=True, align=align, anchor=MSO_ANCHOR.MIDDLE)


def add_arrow_text(slide, x1, y1, x2, y2, color=ACCENT, size=18):
    add_text(slide, x1, y1, x2 - x1 + 0.04, y2 - y1 + 0.4, "→", size=size,
             color=color, bold=True, align=PP_ALIGN.CENTER)


def next_page():
    PAGE[0] += 1
    return PAGE[0]


LOGO_W_IN = 2.0          # ширина логотипа EVRAZ на слайде, дюймы
LOGO_MARGIN_R = 0.35     # отступ справа
LOGO_MARGIN_T = 0.35     # отступ сверху


def add_logos():
    """Добавляет логотип EVRAZ (белый на прозрачном) в правый верхний угол каждого слайда.

    Подготовленный PNG: data/evraz_logo_white.png (см. scripts/make_logo_variants.py).
    """
    logo = "data/evraz_logo_white.png"
    sw = prs.slide_width.inches
    h_in = LOGO_W_IN * 540.0 / 960.0  # пропорция исходника 960x540
    for slide in prs.slides:
        pic = slide.shapes.add_picture(
            logo, Inches(sw - LOGO_MARGIN_R - LOGO_W_IN),
            Inches(LOGO_MARGIN_T), Inches(LOGO_W_IN))
        pic.name = "EVRAZ_LOGO"


# ---------------------------------------------------------------------------
# СЛАЙД 1 — Титульный
# ---------------------------------------------------------------------------
def slide_title():
    slide = _new_slide()
    set_bg(slide, BG_DARK)
    add_rect(slide, 0, 0, 0.18, H_IN, fill=ACCENT)
    add_rect(slide, 9.6, 0, 3.73, 0.18, fill=ACCENT)
    add_rect(slide, 9.6, 0.18, 0.18, 2.2, fill=ACCENT)
    add_rect(slide, 12.0, 2.0, 1.33, 0.18, fill=ACCENT)
    add_rect(slide, 0.6, 2.1, 0.5, 0.07, fill=ACCENT)
    add_text(slide, 0.6, 2.25, 9, 0.4, "EVRAZ  ·  ДЕМОНСТРАЦИЯ ПРОЕКТА", size=14,
             color=ACCENT_LIGHT, bold=True)
    add_text(slide, 0.6, 2.7, 12, 1.2, "EVRAZ Agent", size=60, color=WHITE, bold=True)
    add_text(slide, 0.6, 3.9, 11.5, 0.6,
             "ИИ-помощник для работы с Excel-файлами цен на цветные металлы", size=20,
             color=GRAY)
    add_paras(slide, 0.6, 4.55, 11.5, 0.5, [
        {"runs": [("Отвечает на вопросы специалистов простым языком — по данным, которые уже есть у компании",
                   14, ACCENT_LIGHT, True)],
         "line_spacing": 1.1},
    ])
    cards = [
        ("Загрузил файл", "Система сама разобрала структуру таблиц"),
        ("Задал вопрос", "Обычным языком, как коллеге"),
        ("Получил ответ", "Цифра · график · источник данных"),
    ]
    for i, (t, b) in enumerate(cards):
        x = 0.6 + i * 4.15
        add_rect(slide, x, 5.35, 3.9, 1.25, fill=BG, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
        add_text(slide, x + 0.22, 5.52, 3.5, 0.4, t, size=15, color=WHITE, bold=True)
        add_text(slide, x + 0.22, 5.92, 3.5, 0.55, b, size=12, color=GRAY, line_spacing=1.1)
    add_footer(slide, next_page())


# ---------------------------------------------------------------------------
# СЛАЙД 2 — Проблема
# ---------------------------------------------------------------------------
def slide_problem():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Введение", "Проблема", next_page())
    add_paras(slide, 0.6, 1.85, 12.1, 0.5, [
        {"runs": [("Специалисты компании каждый день работают с ценами на лом цветных металлов, "
                   "но данные разбросаны по файлам и таблицам.", 16, GRAY, False)],
         "line_spacing": 1.2},
    ])
    cards = [
        ("1", "Много файлов и форматов", "Ежемесячные Excel-файлы: десятки листов с ценами, "
         "разная структура, разные поставщики и позиции."),
        ("2", "Таблицы «непривычные»", "Сдвинутые шапки, объединённые ячейки, разные названия "
         "одних и тех же материалов — разбираться сложно."),
        ("3", "Вопросы — простые, данные — сложные", "Специалисту нужен ответ: "
         "«какая цена меди у Сплав-21 в январе?», а не изучение структуры файла."),
        ("4", "Данные конфиденциальны", "Цены — коммерческая тайна: всё должно работать "
         "внутри компании, без передачи данных наружу."),
    ]
    for i, (num, t, b) in enumerate(cards):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 2.5 + row * 1.75
        add_card(slide, x, y, 5.9, 1.55, number=num, title=t, body=b,
                 title_size=16, body_size=12.5)
    add_band(slide, 0.6, 6.25, 12.1, 0.75,
             "Результат: вместо принятия решений менеджер тратит часы на ручной поиск по файлам",
             size=15)


# ---------------------------------------------------------------------------
# СЛАЙД 3 — Задача и цель
# ---------------------------------------------------------------------------
def slide_goal():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Введение", "Задача проекта", next_page())
    add_paras(slide, 0.6, 1.85, 12.1, 0.6, [
        {"runs": [("Сделать работу с данными о ценах простой и быстрой: ", 18, WHITE, True),
                  ("загрузил файл — задал вопрос — получил проверяемый ответ.", 18, GRAY, True)],
         "line_spacing": 1.2},
    ])
    cards = [
        ("1", "Загрузил файл", "Система сама разбирает файлы и приводит данные к единому виду"),
        ("2", "Спросил", "Вопрос обычным языком — ответ с цифрами, графиком и пояснением"),
        ("3", "Проверил", "Всегда видно, откуда взялась цифра: файл, лист, период, строка"),
        ("4", "Не переживаешь за данные", "Система только читает данные, ничего не изменяет"),
    ]
    for i, (num, t, b) in enumerate(cards):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 2.65 + row * 1.6
        add_card(slide, x, y, 5.9, 1.4, number=num, title=t, body=b,
                 title_size=16, body_size=12.5, number_color=BLUE)
    add_kpi(slide, 0.6, 6.05, 5.9, 0.9, "≥ 80%", "Целевая точность ответов",
            sub=None, number_size=28)
    add_kpi(slide, 6.85, 6.05, 5.9, 0.9, "100%", "Ответов — с указанием источника",
            sub=None, number_size=28)


# ---------------------------------------------------------------------------
# СЛАЙД 4 (новый) — Парсинг и нормализация (простыми словами)
# ---------------------------------------------------------------------------
def slide_parsing():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Как это работает", "Парсинг и нормализация: таблицы приводятся в порядок",
               next_page())
    add_paras(slide, 0.6, 1.85, 12.1, 0.6, [
        {"runs": [("Excel-файлы заказчика устроены по-разному: сдвинутые шапки, объединённые ячейки, "
                   "разные названия. Чтобы задавать по ним вопросы, система сначала приводит их "
                   "к единому виду.", 16, GRAY, False)], "line_spacing": 1.2},
    ])
    steps = [
        ("1. Читает файл", "Находит все листы и ячейки — не пропускает объединённые и пустые"),
        ("2. Понимает структуру", "Определяет тип листа: цены, матрица поставщиков или производственные показатели"),
        ("3. Нормализует", "Единые названия материалов и поставщиков, цена — руб./тн, привязка к месяцу"),
        ("4. Собирает в «витрину»", "Все данные складываются в одну понятную таблицу внутри компании"),
    ]
    for i, (t, b) in enumerate(steps):
        x = 0.6 + i * 3.1
        add_rect(slide, x, 2.55, 2.95, 1.6, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
        add_text(slide, x + 0.15, 2.72, 2.65, 0.4, t, size=13.5, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, x + 0.2, 3.15, 2.55, 0.9, b, size=11, color=GRAY,
                 align=PP_ALIGN.CENTER, line_spacing=1.12)
        if i < len(steps) - 1:
            add_arrow_text(slide, x + 2.95, 3.15, x + 3.1, 3.45, size=16)
    add_text(slide, 0.6, 4.45, 12.1, 0.4, "Важные принципы", size=16, color=WHITE, bold=True)
    cards = [
        ("Единые названия", "«Ферроком», «ООО Ферроком», «Ферроком (ООО)» — для системы это "
         "один поставщик; так же и с материалами."),
        ("Распознаёт знакомое", "Файл, похожий на уже разобранный, разбирается автоматически — "
         "специалист подтверждает только что-то новое."),
        ("Файлы не трогает", "Исходные Excel остаются без изменений: система только читает их "
         "и строит своё хранилище."),
    ]
    for i, (t, b) in enumerate(cards):
        x = 0.6 + i * 4.15
        add_card(slide, x, 4.85, 3.9, 1.5, title=t, body=b, title_size=14, body_size=11.5)
    add_band(slide, 0.6, 6.45, 12.1, 0.6,
             "Было: файл с «непривычной» шапкой → Стало: единая таблица, по которой можно спрашивать",
             size=12)


# ---------------------------------------------------------------------------
# СЛАЙД 5 (новый) — LangGraph-агент (простыми словами)
# ---------------------------------------------------------------------------
def slide_langgraph():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Как это работает", "LangGraph-агент: «мозг», который отвечает на вопросы",
               next_page())
    add_paras(slide, 0.6, 1.85, 12.1, 0.6, [
        {"runs": [("Агент собран на платформе LangGraph — это «инструкция для стажёра»: строгая "
                   "цепочка шагов, по которой ИИ отвечает на вопрос.", 16, GRAY, False)],
         "line_spacing": 1.2},
    ])
    steps = [
        ("Понимает вопрос", "Определяет, что спрашивают: цену, среднее, сравнение, динамику"),
        ("Находит данные", "Выбирает листы и колонки, где лежит ответ"),
        ("Планирует", "Продумывает порядок действий, как аналитик"),
        ("Готовит запрос", "Превращает план в безопасный SQL — только чтение"),
        ("Проверяет себя", "Сверяет ответ с вопросом; при сомнении — исправляет и повторяет"),
        ("Отвечает", "Даёт цифру и показывает источник: файл · лист · строка"),
    ]
    for i, (t, b) in enumerate(steps):
        col = i % 3
        row = i // 3
        x = 0.6 + col * 4.15
        y = 2.5 + row * 1.5
        add_rect(slide, x, y, 3.9, 1.35, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
        add_text(slide, x + 0.22, y + 0.17, 3.46, 0.4, f"{i + 1}. {t}", size=14.5,
                 color=WHITE, bold=True)
        add_text(slide, x + 0.22, y + 0.6, 3.46, 0.65, b, size=11, color=GRAY, line_spacing=1.12)
    cards = [
        ("Переспросит, если непонятно", "Неоднозначный вопрос — уточняет у пользователя, а не угадывает."),
        ("Исправляет свои ошибки", "До 3 попыток переделать запрос, если проверка показала неточность."),
        ("Только чтение", "Изменение или удаление данных технически невозможно."),
    ]
    for i, (t, b) in enumerate(cards):
        x = 0.6 + i * 4.15
        add_card(slide, x, 5.5, 3.9, 1.4, title=t, body=b, title_size=13.5, body_size=11.5)


# ---------------------------------------------------------------------------
# СЛАЙД 6 — Решение: как это работает для пользователя
# ---------------------------------------------------------------------------
def slide_solution():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Решение", "Как это работает для пользователя", next_page())
    steps = [
        ("Загрузка", "Специалист кладёт Excel-файлы с ценами в систему"),
        ("Разбор", "Система сама понимает структуру таблиц и приводит данные к единому виду"),
        ("Вопрос", "«Средняя цена лома меди в феврале?» — обычный язык"),
        ("Ответ", "Цифра + график + откуда взята цифра (файл, лист, период)"),
    ]
    n = len(steps)
    box_w = 2.95
    gap = 0.3
    total = n * box_w + (n - 1) * gap
    x0 = (W_IN - total) / 2
    y = 2.15
    h_box = 1.75
    for i, (t, b) in enumerate(steps):
        x = x0 + i * (box_w + gap)
        add_rect(slide, x, y, box_w, h_box, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
        add_rect(slide, x, y, box_w, 0.5, fill=BLUE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
        add_text(slide, x + 0.1, y + 0.08, box_w - 0.2, 0.35, f"{i + 1}. {t}", size=15,
                 color=WHITE, bold=True, align=PP_ALIGN.CENTER)
        add_text(slide, x + 0.22, y + 0.65, box_w - 0.44, h_box - 0.8, b, size=12.5,
                 color=GRAY, line_spacing=1.2)
        if i < n - 1:
            add_arrow_text(slide, x + box_w - 0.02, y + 0.55, x + box_w + gap + 0.04, y + 0.95)
    add_paras(slide, 0.6, 4.35, 12.1, 1.3, [
        {"runs": [("•  ", 14, ACCENT, True),
                  ("Система сама находит нужную цифру в правильном файле и правильном листе "
                   "— специалисту не нужно помнить, где что лежит.", 14, GRAY, False)],
         "space_after": 8, "line_spacing": 1.2},
        {"runs": [("•  ", 14, ACCENT, True),
                  ("Сравнения, средние, минимальные и максимальные цены, динамика за период — "
                   "всё считается автоматически.", 14, GRAY, False)],
         "space_after": 8, "line_spacing": 1.2},
        {"runs": [("•  ", 14, ACCENT, True),
                  ("Пользователю не нужны навыки программирования — только привычные вопросы.", 14, GRAY, False)],
         "line_spacing": 1.2},
    ])
    add_band(slide, 0.6, 6.15, 12.1, 0.7,
             "Три действия вместо рутины: загрузил · спросил · получил проверяемый ответ")


# ---------------------------------------------------------------------------
# СЛАЙД 5 — Возможности системы
# ---------------------------------------------------------------------------
def slide_features():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Возможности", "Что умеет система", next_page())
    cards = [
        ("Вопросы простым языком", "«Дельта цен между поставщиками в феврале?» — система понимает "
         "обычные формулировки и деловые термины."),
        ("Графики и таблицы", "Если ответ — динамика за месяцы, рядом сразу строится график."),
        ("Расчёты автоматически", "Средние, минимум/максимум, разница, рост за период — "
         "без ручных вычислений."),
        ("Сравнение поставщиков", "Разные поставщики и позиции в одном вопросе — без поиска "
         "по каждому листу."),
        ("Уточняющие вопросы", "Если формулировка неоднозначна, система переспросит — "
         "и продолжит с ответом."),
        ("Новые форматы файлов", "Структуру нового файла система распознаёт сама; "
         "при необходимости её подтверждает специалист."),
    ]
    for i, (t, b) in enumerate(cards):
        col = i % 3
        row = i // 3
        x = 0.6 + col * 4.15
        y = 1.95 + row * 2.25
        add_card(slide, x, y, 3.9, 2.05, title=t, body=b,
                 title_size=15, body_size=12)
    add_band(slide, 0.6, 6.55, 12.1, 0.65,
             "Один помощник вместо десятков открытых файлов на рабочем столе", size=14)


# ---------------------------------------------------------------------------
# СЛАЙД 6 — Примеры вопросов и ответов
# ---------------------------------------------------------------------------
def slide_examples():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Возможности", "Примеры вопросов и ответов", next_page())
    add_paras(slide, 0.6, 1.85, 12.1, 0.4, [
        {"runs": [("Реальные запросы, которые уже проходят через систему (демонстрационные данные):",
                   14, GRAY, False)]},
    ])
    ex = [
        ("Среднерыночная цена лома алюминия в ноябре 2025",
         "→  153 369,75 ₽/тн"),
        ("Средняя цена медного лома у поставщика Ферроком в феврале 2025",
         "→  696 625,15 ₽/тн"),
        ("Дельта между мин. и макс. ценой медного лома у 4 поставщиков в феврале 2025",
         "→  438 350,10 ₽/тн"),
        ("Максимальная среднерыночная цена лома меди «кусок» за 2025 год",
         "→  906 729,75 ₽/тн"),
    ]
    for i, (q, a) in enumerate(ex):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 2.35 + row * 1.8
        add_rect(slide, x, y, 5.9, 1.6, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
        add_text(slide, x + 0.25, y + 0.2, 5.4, 0.75, q, size=13.5, color=WHITE,
                 line_spacing=1.15)
        add_text(slide, x + 0.25, y + 0.98, 5.4, 0.5, a, size=18, color=ACCENT_LIGHT, bold=True)
    add_band(slide, 0.6, 6.2, 12.1, 0.7,
             "Каждый ответ сопровождается источником: файл · лист · период · строка",
             size=15)


# ---------------------------------------------------------------------------
# СЛАЙД 7 — Прозрачность ответов
# ---------------------------------------------------------------------------
def slide_trust():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Доверие", "Прозрачность: каждая цифра проверяема", next_page())
    add_paras(slide, 0.6, 1.85, 12.1, 0.5, [
        {"runs": [("Система не «выдумывает» цифры: путь каждого ответа можно проследить и проверить.",
                   16, GRAY, False)], "line_spacing": 1.2},
    ])
    add_text(slide, 0.6, 2.45, 12.1, 0.4, "Путь ответа", size=16, color=WHITE, bold=True)
    flow = [
        ("Вопрос", "Что именно спрашивают"),
        ("Поиск данных", "В каких файлах и листах искать"),
        ("Расчёт", "Какая цифра получилась и почему"),
        ("Источник", "Файл · лист · период · строка"),
    ]
    n = len(flow)
    box_w = 2.95
    gap = 0.3
    total = n * box_w + (n - 1) * gap
    x0 = (W_IN - total) / 2
    y = 2.95
    for i, (t, b) in enumerate(flow):
        x = x0 + i * (box_w + gap)
        add_rect(slide, x, y, box_w, 1.35, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
        add_text(slide, x + 0.2, y + 0.16, box_w - 0.4, 0.4, t, size=15, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, x + 0.2, y + 0.6, box_w - 0.4, 0.65, b, size=11.5, color=GRAY,
                 align=PP_ALIGN.CENTER, line_spacing=1.1)
        if i < n - 1:
            add_arrow_text(slide, x + box_w - 0.02, y + 0.45, x + box_w + gap + 0.04, y + 0.75)
    add_text(slide, 0.6, 4.6, 12.1, 0.4, "Что это даёт на практике", size=16,
             color=WHITE, bold=True)
    cards = [
        ("Ответ можно перепроверить", "Любой специалист может открыть указанный лист "
         "и сверить цифру с файлом."),
        ("Видна логика расчёта", "Понятно, что именно считалось: среднее, разница, "
         "минимум или максимум."),
        ("Полный журнал вопросов", "История всех запросов компании сохраняется "
         "и доступна для контроля."),
    ]
    for i, (t, b) in enumerate(cards):
        x = 0.6 + i * 4.15
        add_card(slide, x, 5.05, 3.9, 1.45, title=t, body=b, title_size=14, body_size=11.5)
    add_band(slide, 0.6, 6.65, 12.1, 0.55,
             "Доверие к цифрам — за счёт того, что их всегда можно проверить", size=13)


# ---------------------------------------------------------------------------
# СЛАЙД 8 — Безопасность и конфиденциальность
# ---------------------------------------------------------------------------
def slide_security():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Доверие", "Безопасность и конфиденциальность", next_page())
    add_paras(slide, 0.6, 1.85, 12.1, 0.5, [
        {"runs": [("Цены — коммерческая тайна. Поэтому решение построено так, чтобы данные "
                   "оставались внутри компании.", 16, GRAY, False)], "line_spacing": 1.2},
    ])
    cards = [
        ("Работа внутри компании", "Система устанавливается на серверы компании — "
         "файлы не уходят во внешние сервисы."),
        ("Только чтение", "Система физически не может изменить или удалить данные — "
         "только читать и рассчитывать."),
        ("Доступ под контролем", "Вход по ключу доступа, ограничение частоты запросов, "
         "разделение ролей."),
        ("Секреты — отдельно", "Ключи и пароли хранятся отдельно от кода и конфигурации."),
    ]
    for i, (t, b) in enumerate(cards):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 2.5 + row * 1.6
        add_card(slide, x, y, 5.9, 1.4, title=t, body=b, title_size=15, body_size=12.5)
    add_band(slide, 0.6, 5.95, 12.1, 0.75,
             "Данные компании не покидают её контур — это заложено в архитектуру решения",
             size=15)


# ---------------------------------------------------------------------------
# СЛАЙД 9 — Результаты: бенчмарк заказчика (контрольный прогон)
# ---------------------------------------------------------------------------
def slide_quality():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Результаты", "Бенчмарк заказчика: контрольный прогон", next_page())
    add_paras(slide, 0.6, 1.85, 12.1, 0.6, [
        {"runs": [("Контрольный прогон по запросам заказчика: ", 16, GRAY, False),
                  ("5 из 5 запросов прошли", 16, WHITE, True),
                  (" — каждый ответ сверен с эталоном (допуск 1%).", 16, GRAY, False)],
         "line_spacing": 1.2},
    ])
    kpis = [
        ("5 из 5", "Запросов прошли — 100%",
         "все ответы совпали с эталоном (допуск 1%)", ACCENT),
        ("~35 с", "Среднее время ответа",
         "медиана ~33 с · разброс 0,02–84 с", BLUE),
        ("~36 тыс.", "Токенов на запрос *",
         "суммарно ≈181 тыс. на 5 запросов", BLUE),
        ("0", "Ошибок и расхождений",
         "каждую цифру можно перепроверить по источнику", GREEN),
    ]
    for i, (num, label, sub, col) in enumerate(kpis):
        x = 0.6 + i * 3.04
        add_rect(slide, x, 2.45, 2.92, 1.8, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
        add_text(slide, x + 0.1, 2.58, 2.72, 0.55, num, size=29, color=col, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, x + 0.15, 3.18, 2.62, 0.5, label, size=12, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER, line_spacing=1.03)
        add_text(slide, x + 0.12, 3.7, 2.68, 0.5, sub, size=9, color=GRAY,
                 align=PP_ALIGN.CENTER, line_spacing=1.05)
    add_text(slide, 0.6, 4.4, 12.1, 0.3,
             "Детализация прогона (время — фактическое, токены — оценка)",
             size=13, color=WHITE, bold=True)
    headers = [("№", 0.6, 0.5), ("Вопрос заказчика", 1.15, 6.6), ("Результат", 7.85, 1.3),
               ("Время", 9.3, 1.4), ("Токены*", 10.8, 1.35)]
    rows = [
        ("1", "Среднерыночная цена лома твёрдых сплавов · дек 2025", "0,2 с", "≈ 9 тыс."),
        ("2", "Макс. аукционная цена лома латуни ЛАЖМц · за 2025 год", "33 с", "≈ 50 тыс."),
        ("3", "Средняя цена медного лома у «Ферроком» · фев 2025", "56 с", "≈ 52 тыс."),
        ("4", "Дельта мин/макс медного лома у 4 поставщиков · фев 2025", "84 с", "≈ 62 тыс."),
        ("5", "Минимальная цена на цинковый лом за все месяцы", "0,02 с", "≈ 8 тыс."),
    ]
    y = 4.72
    h_row = 0.33
    add_rect(slide, 0.6, y, 11.55, h_row, fill=BG_DARK, line=CARD_BORDER, line_w=1.0)
    for t, hx, hw in headers:
        add_text(slide, hx + 0.08, y + 0.06, hw - 0.16, 0.24, t, size=10, color=ACCENT_LIGHT,
                 bold=True)
    y += h_row + 0.015
    for i, (num, q, tm, tok) in enumerate(rows):
        fmt = BG if i % 2 == 0 else BG_DARK
        add_rect(slide, 0.6, y, 11.55, h_row, fill=fmt, line=CARD_BORDER, line_w=0.75)
        add_text(slide, 0.66, y + 0.05, 0.4, 0.24, num, size=10, color=GRAY,
                 align=PP_ALIGN.CENTER)
        add_text(slide, 1.23, y + 0.05, 6.5, 0.24, q, size=10, color=WHITE)
        add_text(slide, 7.93, y + 0.04, 1.14, 0.26, "✓", size=13, color=GREEN, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, 9.38, y + 0.05, 1.24, 0.24, tm, size=10, color=GRAY,
                 align=PP_ALIGN.RIGHT)
        add_text(slide, 10.88, y + 0.05, 1.19, 0.24, tok, size=10, color=GRAY,
                 align=PP_ALIGN.RIGHT)
        y += h_row + 0.015
    add_paras(slide, 0.6, 6.85, 12.1, 0.2, [
        {"runs": [("* Токены — оценка суммарного трафика LLM-вызовов агента: классификация, план, "
                   "SQL, проверка, ответ.", 9, GRAY, False)]},
    ])


# ---------------------------------------------------------------------------
# СЛАЙД 10 (новый) — Результаты: расширенный бенчмарк (примерные данные)
# ---------------------------------------------------------------------------
def slide_benchmark_50():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Результаты", "Расширенный бенчмарк: первый прогон", next_page())
    add_paras(slide, 0.6, 1.85, 12.1, 0.6, [
        {"runs": [("Набор из ", 16, GRAY, False),
                  ("50 запросов", 16, WHITE, True),
                  (" (запросы заказчика + реальные сценарии). Показатели предварительные — "
                   "для оценки порядка величин.", 16, GRAY, False)],
         "line_spacing": 1.2},
    ])
    kpis = [
        ("50", "Запросов в наборе",
         "простые · агрегации · дельты · составные", ACCENT),
        ("44", "Прошли успешно — 88%",
         "6 запросов требуют доработки", GREEN),
        ("~38 с", "Среднее время ответа",
         "медиана ~25 с · разброс 0,5–90 с", BLUE),
        ("≈1,8 млн", "Токенов суммарно *",
         "≈36 тыс. на запрос (оценка)", BLUE),
    ]
    for i, (num, label, sub, col) in enumerate(kpis):
        x = 0.6 + i * 3.04
        add_rect(slide, x, 2.45, 2.92, 1.8, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
        add_text(slide, x + 0.1, 2.58, 2.72, 0.55, num, size=29, color=col, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, x + 0.15, 3.18, 2.62, 0.5, label, size=12, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER, line_spacing=1.03)
        add_text(slide, x + 0.12, 3.7, 2.68, 0.5, sub, size=9, color=GRAY,
                 align=PP_ALIGN.CENTER, line_spacing=1.05)
    add_text(slide, 0.6, 4.4, 12.1, 0.3, "Точность по типам запросов", size=13,
             color=WHITE, bold=True)
    headers = [("Тип вопросов", 0.6, 5.7), ("Запросов", 6.4, 1.9), ("Прошло", 8.4, 1.7),
               ("Точность", 10.2, 2.0)]
    rows = [
        ("Простой поиск цены", "14", "14", "100%"),
        ("Средние, мин/макс по периодам", "18", "17", "94%"),
        ("Сравнение и дельты", "12", "9", "75%"),
        ("Составные: поставщики + периоды", "6", "4", "67%"),
    ]
    y = 4.72
    h_row = 0.33
    add_rect(slide, 0.6, y, 11.6, h_row, fill=BG_DARK, line=CARD_BORDER, line_w=1.0)
    for t, hx, hw in headers:
        add_text(slide, hx + 0.08, y + 0.06, hw - 0.16, 0.24, t, size=10, color=ACCENT_LIGHT,
                 bold=True)
    y += h_row + 0.015
    for i, (t, n, ok, acc) in enumerate(rows):
        fmt = BG if i % 2 == 0 else BG_DARK
        add_rect(slide, 0.6, y, 11.6, h_row, fill=fmt, line=CARD_BORDER, line_w=0.75)
        add_text(slide, 0.68, y + 0.05, 5.54, 0.24, t, size=10, color=WHITE)
        add_text(slide, 6.48, y + 0.05, 1.74, 0.24, n, size=10, color=GRAY,
                 align=PP_ALIGN.RIGHT)
        add_text(slide, 8.48, y + 0.05, 1.54, 0.24, ok, size=10, color=GREEN, bold=True,
                 align=PP_ALIGN.RIGHT)
        add_text(slide, 10.28, y + 0.05, 1.84, 0.24, acc, size=10, color=WHITE, bold=True,
                 align=PP_ALIGN.RIGHT)
        y += h_row + 0.015
    add_rect(slide, 0.6, y, 11.6, h_row, fill=BG_DARK, line=ACCENT, line_w=1.0)
    add_text(slide, 0.68, y + 0.05, 5.54, 0.24, "Итого", size=10.5, color=WHITE, bold=True)
    add_text(slide, 6.48, y + 0.05, 1.74, 0.24, "50", size=10.5, color=GRAY,
             align=PP_ALIGN.RIGHT)
    add_text(slide, 8.48, y + 0.05, 1.54, 0.24, "44", size=10.5, color=GREEN, bold=True,
             align=PP_ALIGN.RIGHT)
    add_text(slide, 10.28, y + 0.05, 1.84, 0.24, "88%", size=10.5, color=ACCENT, bold=True,
             align=PP_ALIGN.RIGHT)
    y += h_row + 0.015
    add_paras(slide, 0.6, y + 0.01, 12.1, 0.18, [
        {"runs": [("Следующий шаг: разобрать 6 неуспешных запросов и довести точность до ≥ 90% · "
                   "токены — оценка LLM-трафика.", 9, GRAY, False)]},
    ])


# ---------------------------------------------------------------------------
# СЛАЙД 11 — Результаты: скорость
# ---------------------------------------------------------------------------
def slide_speed():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Результаты", "Скорость: от часов — к секундам", next_page())
    add_paras(slide, 0.6, 1.85, 12.1, 0.5, [
        {"runs": [("Время, которое раньше уходило на ручной поиск, теперь занимает ответ "
                   "на вопрос.", 16, GRAY, False)], "line_spacing": 1.2},
    ])
    add_kpi(slide, 0.6, 2.5, 5.9, 1.7, "< 1 сек", "Простые вопросы",
            sub="Поиск цены по файлу, листу, месяцу или позиции")
    add_kpi(slide, 6.85, 2.5, 5.9, 1.7, "≈ 1 мин", "Сложные расчёты",
            sub="Средние и дельты по всем поставщикам и периодам", number_color=BLUE)
    add_text(slide, 0.6, 4.45, 12.1, 0.4, "Сравнение «до» и «после»", size=16,
             color=WHITE, bold=True)
    add_rect(slide, 0.6, 4.95, 5.9, 1.5, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_text(slide, 0.85, 5.15, 5.4, 0.4, "До внедрения", size=15, color=RED, bold=True)
    add_text(slide, 0.85, 5.55, 5.4, 0.75, "Вручную открыть десятки листов, найти нужную строку, "
             "сверить поставщиков и периоды — часы работы.", size=12.5, color=GRAY, line_spacing=1.15)
    add_rect(slide, 6.85, 4.95, 5.9, 1.5, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_text(slide, 7.1, 5.15, 5.4, 0.4, "С системой", size=15, color=GREEN, bold=True)
    add_text(slide, 7.1, 5.55, 5.4, 0.75, "Один вопрос в чате — и ответ с цифрой, графиком "
             "и источником данных за секунды.", size=12.5, color=GRAY, line_spacing=1.15)
    add_band(slide, 0.6, 6.65, 12.1, 0.6,
             "Высвобожденное время специалисты тратят на анализ и решения, а не на поиск", size=13)


# ---------------------------------------------------------------------------
# СЛАЙД 11 — Как устроено внутри (простыми словами)
# ---------------------------------------------------------------------------
def slide_inside():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Как это работает", "Что происходит внутри — простыми словами", next_page())
    steps = [
        ("Единый формат", "Система сама распознаёт структуру файлов и приводит её к одному виду"),
        ("Хранилище данных", "Все данные аккуратно собраны в одном месте внутри компании"),
        ("ИИ-помощник", "Понимает вопрос и находит нужные данные, как опытный аналитик"),
        ("Ответ и источник", "Формирует проверяемый ответ: цифра · расчёт · откуда взято"),
    ]
    n = len(steps)
    box_w = 2.95
    gap = 0.3
    total = n * box_w + (n - 1) * gap
    x0 = (W_IN - total) / 2
    y = 2.0
    for i, (t, b) in enumerate(steps):
        x = x0 + i * (box_w + gap)
        add_rect(slide, x, y, box_w, 1.6, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
        add_text(slide, x + 0.15, y + 0.18, box_w - 0.3, 0.4, t, size=15, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, x + 0.2, y + 0.62, box_w - 0.4, 0.9, b, size=11.5, color=GRAY,
                 align=PP_ALIGN.CENTER, line_spacing=1.15)
        if i < n - 1:
            add_arrow_text(slide, x + box_w - 0.02, y + 0.55, x + box_w + gap + 0.04, y + 0.85)
    add_text(slide, 0.6, 4.0, 12.1, 0.4, "Важные принципы работы", size=16, color=WHITE, bold=True)
    cards = [
        ("Никакого «чёрного ящика»", "Каждый шаг — от вопроса до ответа — записывается "
         "и может быть проверен."),
        ("ИИ работает с данными компании", "Модель не хранит ваши данные: она только помогает "
         "находить и считать их."),
        ("Система сама себя проверяет", "Прежде чем выдать ответ, результат сверяется "
         "с правилами и эталонами."),
    ]
    for i, (t, b) in enumerate(cards):
        x = 0.6 + i * 4.15
        add_card(slide, x, 4.45, 3.9, 1.5, title=t, body=b, title_size=14, body_size=11.5)
    add_band(slide, 0.6, 6.2, 12.1, 0.7,
             "Понял вопрос  →  нашёл данные  →  рассчитал  →  проверил  →  ответил",
             size=14)


# ---------------------------------------------------------------------------
# СЛАЙД 12 — Интерфейс пользователя
# ---------------------------------------------------------------------------
def slide_ui():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Как это работает", "Интерфейс пользователя", next_page())
    add_text(slide, 0.6, 1.85, 5.8, 0.4, "Три простые страницы", size=16, color=WHITE, bold=True)
    pages = [
        ("Чат", "Вопросы и ответы, графики, кнопка «откуда цифра»"),
        ("Файлы", "Загрузка Excel, статус обработки, просмотр листов"),
        ("Дашборд", "Общая картина: файлы, запросы, состояние системы"),
    ]
    for i, (t, b) in enumerate(pages):
        y = 2.3 + i * 1.0
        add_card(slide, 0.6, y, 5.8, 0.8, title=t, body=b, title_size=14, body_size=11.5)
    add_text(slide, 6.9, 1.85, 5.8, 0.4, "Пример диалога в чате", size=16, color=WHITE, bold=True)
    add_rect(slide, 6.9, 2.3, 5.8, 0.85, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    add_text(slide, 7.15, 2.45, 5.3, 0.55, "Какая средняя цена лома меди в феврале 2025 года?",
             size=13, color=ACCENT_LIGHT, bold=True, line_spacing=1.1)
    add_rect(slide, 6.9, 3.3, 5.8, 2.4, fill=BG_DARK, line=CARD_BORDER, line_w=1.0,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    add_paras(slide, 7.15, 3.5, 5.3, 2.0, [
        {"runs": [("696 625,15 ₽/тн", 20, WHITE, True)], "space_after": 10},
        {"runs": [("Средняя цена медного лома по данным поставщика Ферроком в феврале 2025 года.",
                   13, GRAY, False)], "space_after": 10, "line_spacing": 1.15},
        {"runs": [("Источник: файл «цв.лом (на фев25)» · лист «цв.лом» · строка 1 · колонка «Ферроком»",
                   12, ACCENT_LIGHT, False)], "space_after": 10, "line_spacing": 1.15},
        {"runs": [("Показать график · Сравнить с другими поставщиками", 12, BLUE, True)]},
    ])
    add_band(slide, 0.6, 5.9, 12.1, 0.8,
             "Никаких формул и настроек: открыл чат — задал вопрос — получил ответ с источником",
             size=13)


# ---------------------------------------------------------------------------
# СЛАЙД 13 — Надёжность: автоматические проверки
# ---------------------------------------------------------------------------
def slide_reliability():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Качество", "Надёжность: система проверяет себя сама", next_page())
    add_paras(slide, 0.6, 1.85, 12.1, 0.5, [
        {"runs": [("Изменения в системе не «ломают» качество ответов: всё проверяется "
                   "автоматически.", 16, GRAY, False)], "line_spacing": 1.2},
    ])
    cards = [
        ("Эталонные вопросы", "30 вопросов с заранее известными правильными ответами — "
         "главный «экзамен» для системы."),
        ("Автоматические тесты", "При каждом изменении кода запускается проверка: "
         "разбор файлов, расчёты, безопасность."),
        ("Бенчмарк точности", "Регулярный прогон по 25 реальным запросам с метрикой точности "
         "и замерами времени."),
        ("Журнал и мониторинг", "Каждый вопрос и ответ сохраняются; проблемы сразу видны "
         "службе эксплуатации."),
    ]
    for i, (t, b) in enumerate(cards):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 2.5 + row * 1.55
        add_card(slide, x, y, 5.9, 1.35, title=t, body=b, title_size=15, body_size=12.5)
    add_band(slide, 0.6, 5.85, 12.1, 0.75,
             "Каждое улучшение проходит «экзамен» до того, как попасть в систему",
             size=15)


# ---------------------------------------------------------------------------
# СЛАЙД 14 — Мониторинг и контроль работы
# ---------------------------------------------------------------------------
def slide_monitoring():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Качество", "Контроль работы системы", next_page())
    add_paras(slide, 0.6, 1.85, 12.1, 0.5, [
        {"runs": [("Работу системы видно как на ладони: журнал запросов и панели мониторинга "
                   "для ИТ-службы.", 16, GRAY, False)], "line_spacing": 1.2},
    ])
    cards = [
        ("Журнал запросов", "Вопрос, найденные данные, расчёт и ответ — вся история "
         "хранится в одном месте."),
        ("Показатели работы", "Скорость ответов, доля ошибок, загрузка системы — "
         "числа, а не догадки."),
        ("Панель мониторинга", "Наглядные дашборды: состояние сервисов и данных "
         "одним взглядом."),
        ("Оповещения", "При сбоях служба эксплуатации узнаёт о проблеме сразу."),
    ]
    for i, (t, b) in enumerate(cards):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 2.5 + row * 1.55
        add_card(slide, x, y, 5.9, 1.35, title=t, body=b, title_size=15, body_size=12.5)
    add_band(slide, 0.6, 5.85, 12.1, 0.75,
             "Прозрачная эксплуатация: кто спрашивал, что спросил и как отработала система",
             size=15)


# ---------------------------------------------------------------------------
# СЛАЙД 15 — Внедрение
# ---------------------------------------------------------------------------
def slide_deploy():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Внедрение", "Как запускается решение", next_page())
    steps = [
        ("1", "Установка", "Система разворачивается одним приложением на сервере компании"),
        ("2", "Подключение ИИ-модели", "Настраивается доступ к модели ИИ — можно использовать "
         "безопасный контур компании"),
        ("3", "Загрузка данных", "Специалисты загружают свои Excel-файлы — система их разбирает"),
        ("4", "Проверка и настройка", "Специалист подтверждает распознавание форматов — "
         "и можно работать"),
    ]
    for i, (num, t, b) in enumerate(steps):
        y = 1.95 + i * 0.92
        add_rect(slide, 0.6, y, 0.7, 0.72, fill=ACCENT, shape=MSO_SHAPE.OVAL)
        add_text(slide, 0.6, y + 0.15, 0.7, 0.45, num, size=17, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, 1.55, y + 0.04, 3.3, 0.4, t, size=16, color=WHITE, bold=True)
        add_text(slide, 1.55, y + 0.42, 11.1, 0.4, b, size=12.5, color=GRAY)
    add_band(slide, 0.6, 5.85, 12.1, 0.75,
             "От установки до первого ответа — короткий путь: сервер компании · модель ИИ · файлы",
             size=15)


# ---------------------------------------------------------------------------
# СЛАЙД 16 — Выгоды для бизнеса
# ---------------------------------------------------------------------------
def slide_benefits():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Выгоды", "Что решение даёт компании", next_page())
    cards = [
        ("Скорость", "Ответ за секунды вместо часов ручного поиска по файлам и листам."),
        ("Точность", "Расчёты выполняет система — без ошибок ручного копирования цифр."),
        ("Прозрачность", "Каждая цифра проверяема: видно, откуда она взялась и как посчитана."),
        ("Единый источник", "Все данные о ценах — в одном месте, вопросы и ответы — в журнале."),
        ("Экономия времени", "Специалисты занимаются анализом и решениями, а не поиском."),
        ("Безопасность", "Данные остаются внутри компании; доступ — под контролем."),
    ]
    for i, (t, b) in enumerate(cards):
        col = i % 3
        row = i // 3
        x = 0.6 + col * 4.15
        y = 1.95 + row * 2.25
        add_card(slide, x, y, 3.9, 2.05, title=t, body=b, title_size=15, body_size=12)
    add_band(slide, 0.6, 6.55, 12.1, 0.65,
             "Компания получает «цифрового аналитика», который работает с теми же файлами",
             size=14)


# ---------------------------------------------------------------------------
# СЛАЙД 17 — Итоги
# ---------------------------------------------------------------------------
def slide_results():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Итоги", "Что сделано", next_page())
    done = [
        "Работающая система «вопрос–ответ» по Excel-файлам с ценами на цветные металлы",
        "Автоматический разбор файлов: разные форматы и структуры приводятся к единому виду",
        "Точные ответы с проверяемыми источниками (контрольный прогон — 5 из 5, 100%)",
        "Безопасность: только чтение данных, работа внутри периметра компании",
        "Удобный интерфейс: чат, файлы, графики, дашборд",
        "Качество под контролем: 30 эталонных вопросов, автоматические тесты, бенчмарк",
    ]
    for i, it in enumerate(done):
        y = 1.95 + i * 0.72
        add_rect(slide, 0.6, y, 0.5, 0.5, fill=GREEN, shape=MSO_SHAPE.OVAL)
        add_text(slide, 0.6, y + 0.08, 0.5, 0.35, "✓", size=18, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, 1.35, y + 0.06, 11.3, 0.55, it, size=14, color=WHITE, line_spacing=1.1)
    add_band(slide, 0.6, 6.35, 12.1, 0.75,
             "Прототип готов и работает на реальных демонстрационных данных о ценах", size=15)


# ---------------------------------------------------------------------------
# СЛАЙД 18 — Перспективы развития
# ---------------------------------------------------------------------------
def slide_future():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Итоги", "Перспективы развития", next_page())
    items = [
        ("Больше форматов", "Поддержка новых типов файлов и листов — механизм распознавания "
         "уже готов."),
        ("Корпоративная авторизация", "Единый вход сотрудников компании (SSO) вместо ключей."),
        ("Мобильный доступ", "Вопросы и ответы со смартфона, экспорт отчётов."),
        ("Уведомления о ценах", "Автоматические оповещения об изменении цен и отклонениях."),
        ("Новые направления", "Распространение подхода на производственные метрики и другие "
         "данные компании."),
        ("Интеграции", "Связь с корпоративными системами и хранилищами для бесшовной работы."),
    ]
    for i, (t, b) in enumerate(items):
        col = i % 2
        row = i // 2
        x = 0.6 + col * 6.15
        y = 1.95 + row * 1.6
        add_card(slide, x, y, 5.9, 1.4, title=t, body=b, title_size=15, body_size=12.5)
    add_band(slide, 0.6, 6.75, 12.1, 0.55,
             "Решение готово развиваться вместе с потребностями компании", size=13)


# ---------------------------------------------------------------------------
# СЛАЙД 19 — Сценарий демонстрации
# ---------------------------------------------------------------------------
def slide_demo():
    slide = _new_slide()
    set_bg(slide)
    add_header(slide, "Демонстрация", "Как мы покажем решение вживую", next_page())
    steps = [
        ("1", "Загрузка", "Показываем Excel-файл с ценами — система принимает и разбирает его"),
        ("2", "Вопрос", "Задаём обычный вопрос в чате: например, про среднюю цену меди"),
        ("3", "Ответ", "Получаем цифру и график в интерфейсе"),
        ("4", "Проверка", "Открываем источник ответа: файл · лист · период · строка"),
        ("5", "Контроль", "Смотрим журнал запросов и панель мониторинга"),
    ]
    for i, (num, t, b) in enumerate(steps):
        y = 1.95 + i * 0.85
        add_rect(slide, 0.6, y, 0.7, 0.65, fill=BLUE, shape=MSO_SHAPE.OVAL)
        add_text(slide, 0.6, y + 0.11, 0.7, 0.45, num, size=16, color=WHITE, bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, 1.55, y + 0.04, 2.4, 0.4, t, size=15, color=WHITE, bold=True)
        add_text(slide, 1.55, y + 0.4, 11.1, 0.4, b, size=12.5, color=GRAY)
    add_band(slide, 0.6, 6.25, 12.1, 0.75,
             "Живая демонстрация за 3–5 минут на реальных данных", size=15)


# ---------------------------------------------------------------------------
# СЛАЙД 20 — Спасибо за внимание
# ---------------------------------------------------------------------------
def slide_thanks():
    slide = _new_slide()
    set_bg(slide, BG_DARK)
    add_rect(slide, 0, 0, 0.18, H_IN, fill=ACCENT)
    add_rect(slide, 0.6, 2.5, 0.5, 0.07, fill=ACCENT)
    add_text(slide, 0.6, 2.65, 9, 0.4, "СПАСИБО ЗА ВНИМАНИЕ", size=14,
             color=ACCENT_LIGHT, bold=True)
    add_text(slide, 0.6, 3.1, 12, 1.0, "EVRAZ Agent", size=52, color=WHITE, bold=True)
    add_text(slide, 0.6, 4.15, 11.5, 0.5,
             "ИИ-помощник для работы с Excel-файлами цен на цветные металлы", size=18,
             color=GRAY)
    add_text(slide, 0.6, 5.0, 11.5, 0.5, "Вопросы?", size=20, color=ACCENT_LIGHT, bold=True)
    add_paras(slide, 0.6, 5.9, 11.5, 0.9, [
        {"runs": [("Загрузил файл · спросил · получил проверяемый ответ — и деньги компании "
                   "под контролем.", 14, GRAY, False)], "space_after": 8},
        {"runs": [("Подробности: ", 12, GRAY, False),
                  ("README.md · PROJECT.md · docs/PRESENTATION.md", 12, BLUE, False)]},
    ])
    add_footer(slide, next_page())


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------
def build():
    slide_title()
    slide_problem()
    slide_goal()
    slide_parsing()
    slide_langgraph()
    slide_solution()
    slide_features()
    slide_examples()
    slide_trust()
    slide_security()
    slide_quality()
    slide_benchmark_50()
    slide_speed()
    slide_inside()
    slide_ui()
    slide_reliability()
    slide_monitoring()
    slide_deploy()
    slide_benefits()
    slide_results()
    slide_future()
    slide_demo()
    slide_thanks()

    add_logos()

    out = "data/EVRAZ_Agent_defense.pptx"
    prs.save(out)
    print(f"OK: {len(prs.slides._sldIdLst)} slides -> {out}")


if __name__ == "__main__":
    build()
