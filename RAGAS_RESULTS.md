# RAGAS Results

## 2026-03-27 — session_guides_smart (2 вопроса)

| Метрика            | Score |
|--------------------|-------|
| faithfulness       | 0.692 |
| answer_relevancy   | 0.767 |
| context_precision  | 1.000 |

**Коллекция:** `session_guides_smart`
**Модель:** `gemini-3-flash-preview`
**Эмбеддинги:** `gemini-embedding-2-preview`
**Книги:** `joyce_sills.pdf`, `mann_100_key_points.pdf`

### Интерпретация
- `context_precision: 1.0` — Qdrant находит только нужные чанки, мусора нет
- `answer_relevancy: 0.767` — ответы в целом по теме, есть куда расти
- `faithfulness: 0.692` — ~30% утверждений в ответах не подкреплены контекстом (галлюцинации или выводы из общих знаний модели)
