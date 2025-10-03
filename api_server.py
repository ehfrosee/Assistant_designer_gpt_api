# -*- coding: utf-8 -*-
"""API сервер для нейро-консультанта"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
import os

from assistant import Assistant

# Инициализация FastAPI приложения
app = FastAPI(
    title="Neuro Consultant API", 
    description="API сервис для нейро-консультанта по проектной документации",
    version="1.0.0"
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация ассистента
try:
    assistant = Assistant()
    print("Ассистент успешно инициализирован")
except Exception as e:
    print(f"Ошибка инициализации ассистента: {e}")
    assistant = None

# Модели данных
class QuestionRequest(BaseModel):
    question: str
    temperature: Optional[float] = None

class QuestionResponse(BaseModel):
    answer: str
    question: str
    tokens_used: int
    sources: List[Dict[str, Any]]
    error: Optional[str] = None

class SummarizeRequest(BaseModel):
    dialog: str

class SummarizeResponse(BaseModel):
    summary: str
    original_length: int
    summary_length: int

class KnowledgeBaseInfo(BaseModel):
    name: str
    description: str
    documents_count: int
    data_path: str
    index_path: str
    status: str
    gpt_model: str
    embedding_model: str

class RebuildResponse(BaseModel):
    status: str
    message: str
    documents_count: int

# API endpoints
@app.post("/api/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest):
    """Задать вопрос ассистенту"""
    if not assistant:
        raise HTTPException(status_code=500, detail="Ассистент не инициализирован")
    
    try:
        result = assistant.ask_question(
            question=request.question,
            temperature=request.temperature
        )
        
        return QuestionResponse(
            answer=result['answer'],
            question=result['question'],
            tokens_used=result['tokens_used'],
            sources=result['sources'],
            error=result.get('error')
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки вопроса: {str(e)}")

@app.post("/api/summarize", response_model=SummarizeResponse)
async def summarize_dialog(request: SummarizeRequest):
    """Суммаризация диалога"""
    if not assistant:
        raise HTTPException(status_code=500, detail="Ассистент не инициализирован")
    
    try:
        summary = assistant.summarize_dialog(request.dialog)
        return SummarizeResponse(
            summary=summary,
            original_length=len(request.dialog),
            summary_length=len(summary)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка суммаризации: {str(e)}")

@app.get("/api/knowledge-base/info", response_model=KnowledgeBaseInfo)
async def get_knowledge_base_info():
    """Получить информацию о базе знаний"""
    if not assistant:
        raise HTTPException(status_code=500, detail="Ассистент не инициализирован")
    
    try:
        info = assistant.get_knowledge_base_info()
        return KnowledgeBaseInfo(**info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения информации: {str(e)}")

@app.post("/api/knowledge-base/rebuild", response_model=RebuildResponse)
async def rebuild_knowledge_base():
    """Перестроить базу знаний"""
    if not assistant:
        raise HTTPException(status_code=500, detail="Ассистент не инициализирован")
    
    try:
        result = assistant.rebuild_knowledge_base()
        return RebuildResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка перестроения базы: {str(e)}")

@app.get("/api/health")
async def health_check():
    """Проверка состояния сервиса"""
    status = "healthy" if assistant and assistant.knowledge_base.index is not None else "unhealthy"
    
    return {
        "status": status,
        "assistant_initialized": assistant is not None,
        "knowledge_base_loaded": assistant.knowledge_base.index is not None if assistant else False
    }

@app.get("/api/")
async def api_root():
    """Корневой endpoint API"""
    return {
        "message": "Neuro Consultant API", 
        "version": "1.0.0",
        "endpoints": {
            "ask": "/api/ask",
            "summarize": "/api/summarize",
            "knowledge_base_info": "/api/knowledge-base/info",
            "knowledge_base_rebuild": "/api/knowledge-base/rebuild",
            "health": "/api/health",
            "docs": "/docs"
        }
    }

@app.get("/")
async def root():
    """Корневой endpoint"""
    return {
        "message": "Neuro Consultant API Server", 
        "version": "1.0.0",
        "api_base": "/api/"
    }

def main():
    """Запуск сервера"""
    config = assistant.config if assistant else {}
    api_config = config.get('api', {})
    
    uvicorn.run(
        app, 
        host=api_config.get('host', '0.0.0.0'), 
        port=api_config.get('port', 5000)
    )

if __name__ == "__main__":
    main()