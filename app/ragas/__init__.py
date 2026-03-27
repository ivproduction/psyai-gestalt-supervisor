"""
app/ragas/ — оценка качества RAG через RAGAS.

  questions.py  — список тест-вопросов (редактируй здесь)
  eval.py       — логика оценки
"""
from app.ragas.eval import evaluate_rag

__all__ = ["evaluate_rag"]
