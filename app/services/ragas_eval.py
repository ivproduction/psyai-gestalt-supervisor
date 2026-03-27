"""
services/ragas_eval.py — оценка качества RAG через RAGAS.

Метрики (без ground truth):
  - faithfulness       — ответ основан на контексте, без галлюцинаций
  - answer_relevancy   — ответ релевантен вопросу
  - context_precision  — retrieved чанки действительно нужны для ответа

Judge LLM: Gemini 2.0 Flash
"""

import logging
from typing import Literal

from datasets import Dataset
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from ragas import evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics import answer_relevancy, context_precision, faithfulness

from app.config import GEMINI_API_KEY, RAG_RESPONSE_MODEL, TOP_K
from app.services.rag import ask as rag_ask

log = logging.getLogger(__name__)

DEFAULT_QUESTIONS = [
    "Что такое феноменологический метод в гештальт-терапии?",
    "Как начать первую сессию с клиентом?",
    "Что такое контакт в гештальт-терапии?",
    "Как работать с сопротивлением клиента?",
    "Что такое незавершённый гештальт?",
]


def _get_ragas_llm():
    llm = ChatGoogleGenerativeAI(
        model=RAG_RESPONSE_MODEL,
        google_api_key=GEMINI_API_KEY,
        temperature=0,
    )
    return LangchainLLMWrapper(llm)


def _get_ragas_embeddings():
    emb = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=GEMINI_API_KEY,
    )
    return LangchainEmbeddingsWrapper(emb)


async def evaluate_rag(
    questions: list[str] | None = None,
    source_type: str = "session_guides",
    mode: Literal["standard", "smart"] = "smart",
    top_k: int = TOP_K,
) -> dict:
    """
    Запускает RAGAS оценку по списку вопросов.
    Если questions=None — использует DEFAULT_QUESTIONS.
    """
    if not questions:
        questions = DEFAULT_QUESTIONS

    log.info("=== RAGAS START: %d вопросов, коллекция=%s_%s ===",
             len(questions), source_type, mode)

    # Собираем данные: для каждого вопроса получаем ответ + чанки
    all_questions, all_answers, all_contexts = [], [], []

    for i, question in enumerate(questions, 1):
        log.info("  [%d/%d] %s...", i, len(questions), question[:60])
        try:
            result = await rag_ask(
                question=question,
                source_type=source_type,
                mode=mode,
                top_k=top_k,
            )
            # Получаем контексты напрямую из поиска
            from app.services.search import search
            chunks = search(query=question, source_type=source_type, mode=mode, top_k=top_k)
            contexts = [c["text"] for c in chunks]

            all_questions.append(question)
            all_answers.append(result["answer"])
            all_contexts.append(contexts)
            log.info("    ✅ ответ=%d симв., контекстов=%d", len(result["answer"]), len(contexts))
        except Exception as e:
            log.warning("    ❌ ошибка: %s", e)

    if not all_questions:
        raise RuntimeError("Не удалось получить ни одного ответа")

    # RAGAS Dataset
    dataset = Dataset.from_dict({
        "question": all_questions,
        "answer": all_answers,
        "contexts": all_contexts,
    })

    log.info("  Запускаю RAGAS evaluate (judge: %s)...", RAG_RESPONSE_MODEL)

    ragas_llm = _get_ragas_llm()
    ragas_emb = _get_ragas_embeddings()

    metrics = [faithfulness, answer_relevancy, context_precision]
    for m in metrics:
        m.llm = ragas_llm
        if hasattr(m, "embeddings"):
            m.embeddings = ragas_emb

    result = evaluate(dataset=dataset, metrics=metrics)
    scores = result.to_pandas()[
        ["faithfulness", "answer_relevancy", "context_precision"]
    ].mean().to_dict()

    log.info("=== RAGAS DONE ===")
    log.info("  faithfulness     : %.3f", scores.get("faithfulness", 0))
    log.info("  answer_relevancy : %.3f", scores.get("answer_relevancy", 0))
    log.info("  context_precision: %.3f", scores.get("context_precision", 0))

    # Детализация по вопросам
    df = result.to_pandas()
    details = []
    for _, row in df.iterrows():
        details.append({
            "question": row["question"],
            "answer_preview": row["answer"][:150],
            "faithfulness": round(row.get("faithfulness", 0), 3),
            "answer_relevancy": round(row.get("answer_relevancy", 0), 3),
            "context_precision": round(row.get("context_precision", 0), 3),
        })

    return {
        "collection": f"{source_type}_{mode}",
        "questions_evaluated": len(all_questions),
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "details": details,
    }
