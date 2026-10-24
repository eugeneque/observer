"""Разбор ответа ИИ на разделы, чтобы 1С могла работать с итогом без анализа текста."""
import re

VERDICTS = [
    ("Сотрудничество не рекомендуется", r"не\s+рекомендуется"),
    ("Требуются обеспечительные меры", r"обеспечительн"),
    ("Сотрудничество безопасно", r"безопасно"),
]
MEASURES = [
    ("Банковская гарантия", r"банковск\w*\s+гаранти"),
    ("Аккредитив", r"аккредитив"),
    ("Залог", r"залог"),
    ("Предоплата", r"предоплат|авансов"),
    ("Поручительство", r"поручительств"),
]
SECTIONS = {
    "Основания": r"основания\s+для\s+заключения",
    "Итог": r"итог",
    "Подписант": r"подписант",
}


def _clean(s: str) -> str:
    s = re.sub(r"[*#`]+", "", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    return s.strip(" \n:—-")


def split_sections(text: str) -> dict[str, str]:
    marks = []
    for key, pat in SECTIONS.items():
        # Заголовок раздела: в начале строки, возможно с номером и разметкой, заканчивается двоеточием
        m = re.search(rf"(?im)^[\s>*#\d.)\"«]*{pat}[\s*\"»]*:", text)
        if m:
            marks.append((m.start(), m.end(), key))
    marks.sort()
    out = {}
    for i, (_, end, key) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out[key] = _clean(text[end:stop])
    return out


def parse_conclusion(text: str) -> dict:
    sections = split_sections(text)
    verdict_text = sections.get("Итог", "")
    verdict = None
    first_line = verdict_text.split("\n", 1)[0].lower()
    for label, pat in VERDICTS:  # сначала смотрим первую строку итога, затем весь раздел
        if re.search(pat, first_line):
            verdict = label
            break
    if verdict is None:
        for label, pat in VERDICTS:
            if re.search(pat, verdict_text.lower()):
                verdict = label
                break
    measures = []
    if verdict == "Требуются обеспечительные меры":
        measures = [label for label, pat in MEASURES if re.search(pat, verdict_text.lower())]
    return {
        "Основания": sections.get("Основания", ""),
        "Итог": verdict or "",
        "ИтогТекст": verdict_text,
        "ОбеспечительныеМеры": measures,
        "Подписант": sections.get("Подписант", ""),
    }
