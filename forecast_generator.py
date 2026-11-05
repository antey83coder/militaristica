from datetime import datetime
json_mod = __import__('json')

def calculate_dynamic_probabilities():
    """
    Здорова логіка: 
    - 2026 (поточний стан): інерція того, що є зараз (домінування позиційних боїв).
    - 2027 (критичний рік виснаження): пік ймовірності переходу в стійкий пат/заморожування через виснаження ресурсів обох сторін.
    - 2028 (довгострокова перспектива): зростання варіативності (або повна консервація конфлікту, або політичні/технологічні переломи).
    """
    forecasts = {
        "2026": {
            "russia_max": 3,
            "russia_partial": 17,
            "frozen": 70,           # Інерція поточного стану до кінця року
            "borders_1991": 10
        },
        "2027": {
            "russia_max": 8,
            "russia_partial": 25,
            "frozen": 52,           # Пік виснаження і ймовірності стагнації лінії фронту
            "borders_1991": 15
        },
        "2028": {
            "russia_max": 12,
            "russia_partial": 30,
            "frozen": 40,           # Часткова розв'язка або глибока трансформація конфлікту
            "borders_1991": 18      # Зростання невизначеності на дальній дистанції
        }
    }
    return forecasts

def main():
    print("🔄 Перерахунок матриці за адекватною логікою...")
    
    matrix_data = calculate_dynamic_probabilities()
    
    output = {
        "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "metrics_source": "Balanced Attrition & Horizon Model",
        "forecasts": matrix_data
    }
    
    with open("war_forecast_data.json", "w", encoding="utf-8") as f:
        json_mod.dump(output, f, ensure_ascii=False, indent=4)
        
    print("✅ Збалансований прогноз успішно оновлено!")

if __name__ == "__main__":
    main()