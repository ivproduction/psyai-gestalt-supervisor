"""
app/ragas/eval.py — логика RAGAS оценки.

Метрики (без ground truth):
  - faithfulness       — ответ основан на контексте, без галлюцинаций
  - answer_relevancy   — ответ релевантен вопросу
  - context_precision  — retrieved чанки действительно нужны для ответа
"""

import asyncio
import json
import logging
import math
import threading
from datetime import datetime
from typing import Literal

from datasets import Dataset
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from ragas import evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics._faithfulness import Faithfulness
from ragas.metrics._answer_relevance import AnswerRelevancy
from ragas.metrics._context_precision import LLMContextPrecisionWithoutReference

from app.config import EMBEDDING_MODEL, GEMINI_API_KEY, RAGAS_DIR, RAGAS_MODEL, TOP_K
from app.services.cache import delete_cached
from app.services.rag import ask as rag_ask
from app.services.search import search
from app.ragas.questions import QUESTIONS

log = logging.getLogger(__name__)


def _get_ragas_llm():
    llm = ChatGoogleGenerativeAI(
        model=RAGAS_MODEL,
        google_api_key=GEMINI_API_KEY,
        temperature=0,
    )
    return LangchainLLMWrapper(llm)


def _get_ragas_embeddings():
    emb = GoogleGenerativeAIEmbeddings(
        model=f"models/{EMBEDDING_MODEL}",
        google_api_key=GEMINI_API_KEY,
        task_type="retrieval_document",
    )
    return LangchainEmbeddingsWrapper(emb)


async def evaluate_rag(
    questions: list[str] | None = None,
    source_type: str = "session_guides",
    mode: Literal["standard", "smart"] = "smart",
    top_k: int = TOP_K,
) -> dict:
    if not questions:
        log.info("  вопросы не переданы → используем QUESTIONS из questions.py")
        questions = QUESTIONS

    log.info("=== RAGAS START: %d вопросов, коллекция=%s_%s ===",
             len(questions), source_type, mode)

    all_questions, all_answers, all_contexts = [], [], []

    for i, question in enumerate(questions, 1):
        log.info("  [%d/%d] %s...", i, len(questions), question[:60])
        try:
            await delete_cached(question)
            result = await rag_ask(question=question, source_type=source_type, mode=mode, top_k=top_k, use_cache=False, channel="telegram")
            chunks = search(query=question, source_type=source_type, mode=mode, top_k=top_k)

            all_questions.append(question)
            all_answers.append(result["answer"])
            all_contexts.append([c["text"] for c in chunks])
            log.info("    ✅ ответ=%d симв., контекстов=%d", len(result["answer"]), len(chunks))
        except Exception as e:
            log.warning("    ❌ ошибка: %s", e)

    if not all_questions:
        raise RuntimeError("Не удалось получить ни одного ответа")

    dataset = Dataset.from_dict({
        "user_input": all_questions,
        "response": all_answers,
        "retrieved_contexts": all_contexts,
    })

    log.info("  Запускаю RAGAS evaluate (judge: %s)...", RAGAS_MODEL)

    ragas_llm = _get_ragas_llm()
    ragas_emb = _get_ragas_embeddings()

    loop = asyncio.get_event_loop()
    future = loop.create_future()

    def _run():
        try:
            res = evaluate(
                dataset=dataset,
                metrics=[
                    Faithfulness(llm=ragas_llm),
                    AnswerRelevancy(llm=ragas_llm, embeddings=ragas_emb),
                    LLMContextPrecisionWithoutReference(llm=ragas_llm),
                ],
                show_progress=False,
            )
            loop.call_soon_threadsafe(future.set_result, res)
        except Exception as e:
            loop.call_soon_threadsafe(future.set_exception, e)

    threading.Thread(target=_run, daemon=True).start()
    result = await future

    _ctx_col = "llm_context_precision_without_reference"

    def _safe(v):
        return None if isinstance(v, float) and math.isnan(v) else round(v, 3)

    def _fmt(v):
        return f"{v:.3f}" if v is not None else "nan(ошибка парсинга LLM)"

    try:
        df = result.to_pandas()
        scores = df[["faithfulness", "answer_relevancy", _ctx_col]].mean().to_dict()
        scores["context_precision"] = scores.pop(_ctx_col)
        scores = {k: _safe(v) for k, v in scores.items()}
        details = [
            {
                "question": row["user_input"],
                "answer_preview": row["response"][:150],
                "faithfulness": _safe(row.get("faithfulness", float("nan"))),
                "answer_relevancy": _safe(row.get("answer_relevancy", float("nan"))),
                "context_precision": _safe(row.get(_ctx_col, float("nan"))),
            }
            for _, row in df.iterrows()
        ]
    except Exception as e:
        log.error("=== RAGAS PARSE ERROR: %s ===", e)
        raise

    log.info("=== RAGAS DONE ===")
    log.info("  faithfulness     : %s", _fmt(scores.get("faithfulness")))
    log.info("  answer_relevancy : %s", _fmt(scores.get("answer_relevancy")))
    log.info("  context_precision: %s", _fmt(scores.get("context_precision")))

    report = {
        "timestamp": datetime.now().isoformat(),
        "collection": f"{source_type}_{mode}",
        "questions_evaluated": len(all_questions),
        "scores": scores,
        "details": details,
    }

    try:
        RAGAS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = RAGAS_DIR / f"{source_type}_{mode}_{ts}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("  💾 результат сохранён: %s", report_path)
    except Exception as e:
        log.error("  ❌ ошибка сохранения результата: %s", e)

    return report
