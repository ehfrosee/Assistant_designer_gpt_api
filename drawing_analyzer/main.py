# Быстрый анализ чертежа
from drawing_analyzer import DrawingAnalyzer

analyzer = DrawingAnalyzer()
results = analyzer.process_drawing("чертеж.pdf")

# Получение данных для GPT
gpt_data = results['gpt_ready_data']

# Экспорт в JSON для последующего анализа
import json
with open('analysis_result.json', 'w', encoding='utf-8') as f:
    json.dump(gpt_data, f, ensure_ascii=False, indent=2)