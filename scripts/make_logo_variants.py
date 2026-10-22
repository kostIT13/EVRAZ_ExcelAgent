# -*- coding: utf-8 -*-
"""Подготовка вариантов логотипа EVRAZ с прозрачным фоном для тёмной темы.

Исходник: data/Evraz-1.jpg.960x540_q95_crop_upscale.jpg (960x540, белый фон).

Что делает:
- Удаляет белый фон (flood-fill от границ) + мягкая кромка по антиалиасингу.
- Прозрачными делает и ВНУТРЕННИЕ белые полости (контры литер В, Р, А и т.п.),
  но сохраняет белые элементы дизайна внутри оранжевого квадрата
  (белая буква «E» в иконке), определяя их по оранжевому окружению.
- Вариант для тёмной темы: тёмно-нейтральный текст перекрашивается в белый.

Результат:
- data/evraz_logo_transparent.png — оригинальные цвета + прозрачный фон.
- data/evraz_logo_white.png — белый текст + оранжевый квадрат.
"""
from collections import deque

import numpy as np
from PIL import Image

SRC = "data/Evraz-1.jpg.960x540_q95_crop_upscale.jpg"
OUT_ORIG = "data/evraz_logo_transparent.png"
OUT_WHITE = "data/evraz_logo_white.png"

BG_WHITE_THRESHOLD = 198   # min(r,g,b) >= этого -> пиксель считается белым фоном
KEEP_ORANGE_RADIUS = 4     # радиус анализа окружения для белых полостей (px)


def flood_fill_from_edges(bgmask):
    """Белые пиксели, достижимые от границ через соседние белые пиксели."""
    h, w = bgmask.shape
    reached = np.zeros_like(bgmask)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if bgmask[y, x] and not reached[y, x]:
                reached[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if bgmask[y, x] and not reached[y, x]:
                reached[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        if y > 0 and bgmask[y - 1, x] and not reached[y - 1, x]:
            reached[y - 1, x] = True
            q.append((y - 1, x))
        if y < h - 1 and bgmask[y + 1, x] and not reached[y + 1, x]:
            reached[y + 1, x] = True
            q.append((y + 1, x))
        if x > 0 and bgmask[y, x - 1] and not reached[y, x - 1]:
            reached[y, x - 1] = True
            q.append((y, x - 1))
        if x < w - 1 and bgmask[y, x + 1] and not reached[y, x + 1]:
            reached[y, x + 1] = True
            q.append((y, x + 1))
    return reached


def dilate(mask, radius=1):
    """Морфологическое расширение (8-окрестность), итерациями."""
    out = mask.copy()
    for _ in range(radius):
        padded = np.pad(out, 1, mode="constant")
        out = (
            padded[0:-2, 1:-1] | padded[2:, 1:-1] | padded[1:-1, 0:-2]
            | padded[1:-1, 2:] | padded[0:-2, 0:-2] | padded[0:-2, 2:]
            | padded[2:, 0:-2] | padded[2:, 2:]
        )
    return out


def label_components(binary):
    """Метки связных областей (8-связность). Возвращает (labels, count)."""
    h, w = binary.shape
    labels = np.zeros((h, w), dtype=np.int64)
    cur = 0
    for y in range(h):
        for x in range(w):
            if binary[y, x] and labels[y, x] == 0:
                cur += 1
                q = deque([(y, x)])
                labels[y, x] = cur
                while q:
                    cy, cx = q.popleft()
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            if dy == 0 and dx == 0:
                                continue
                            ny, nx = cy + dy, cx + dx
                            if (0 <= ny < h and 0 <= nx < w and binary[ny, nx]
                                    and labels[ny, nx] == 0):
                                labels[ny, nx] = cur
                                q.append((ny, nx))
    return labels, cur


def decide_interior_white(interior_white, orange, not_bg):
    """Возвращает маску "дизайн-белого" (оставить) и маску "полостей" (удалить).

    Белые полости, окружённые преимущественно оранжевым контентом, —
    это белые элементы внутри оранжевого квадрата (буква «E»): оставляем.
    Остальные (литеральные контры В/Р/А и т.п.) — прозрачные.
    """
    labels, n = label_components(interior_white)
    keep = np.zeros_like(interior_white)
    remove = np.zeros_like(interior_white)
    bg = ~not_bg
    for comp in range(1, n + 1):
        cmask = labels == comp
        ring = dilate(cmask, KEEP_ORANGE_RADIUS) & ~cmask & not_bg
        if ring.sum() == 0:
            remove |= cmask
            continue
        n_orange = ring & orange
        n_other = ring & ~orange
        if n_orange.sum() * 3 > n_other.sum():
            keep |= cmask        # белый элемент внутри оранжевого квадрата
        else:
            remove |= cmask      # полость в букве
    return keep, remove


def apply_fix(rgb):
    """Общая обработка: прозрачный фон + корректные полости букв."""
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    minc = np.minimum(np.minimum(r, g), b)

    bgmask = minc >= BG_WHITE_THRESHOLD          # все белые пиксели
    edge_bg = flood_fill_from_edges(bgmask)      # фон от краёв
    interior_white = bgmask & ~edge_bg           # замкнутые белые полости
    not_bg = ~bgmask                             # контент

    orange = ((r > 170) & (g > 50) & (g < 210) & (b < 130))

    keep_white, remove_white = decide_interior_white(
        interior_white, orange, not_bg)

    transparent = edge_bg | remove_white         # всё, что станет прозрачным

    alpha = np.full(rgb.shape[:2], 255, dtype=np.uint8)
    alpha[transparent] = 0

    # Мягкая кромка на границе прозрачного
    edge = dilate(transparent, 1) & ~transparent
    scale = 255.0 / (255.0 - BG_WHITE_THRESHOLD)
    a_edge = np.clip((255 - minc) * scale, 0, 255).astype(np.uint8)
    a_edge[minc < BG_WHITE_THRESHOLD] = 255
    alpha[edge] = a_edge[edge]
    return alpha, keep_white, remove_white


def main():
    im = Image.open(SRC).convert("RGB")
    arr = np.asarray(im, dtype=np.uint8)
    alpha, keep_white, remove_white = apply_fix(arr)
    print(f"полостей букв удалено: {int(remove_white.sum())} px, "
          f"дизайн-белого сохранено: {int(keep_white.sum())} px")

    # --- вариант 1: оригинальные цвета + прозрачный фон ---
    rgba = np.dstack([arr, alpha])
    Image.fromarray(rgba, "RGBA").save(OUT_ORIG)
    print("saved", OUT_ORIG)

    # --- вариант 2: тёмный текст -> белый ---
    out = arr.copy()
    r = out[..., 0].astype(np.int16)
    g = out[..., 1].astype(np.int16)
    b = out[..., 2].astype(np.int16)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    sat = mx - mn
    alpha_mask = alpha > 128
    recolor = alpha_mask & (sat < 45) & (mx < 110)
    out[recolor] = (255, 255, 255)
    print(f"перекрашено в белый: {int(recolor.sum())} px")
    rgba2 = np.dstack([out, alpha])
    Image.fromarray(rgba2, "RGBA").save(OUT_WHITE)
    print("saved", OUT_WHITE)


if __name__ == "__main__":
    main()