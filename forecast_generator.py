from datetime import datetime
import json

def generate_dynamic_forecasts():
    """
    Повністю динамічна модель з урахуванням системного часу (rolling horizon) та часового затухання (time-decay):
    - Автоматично визначає поточний рік і будує прогноз на 3 роки вперед.
    - Розраховує залишок днів до кінця поточного року та пропорційно масштабує ймовірності.
    - Оперує незалежними величинами з двома знаками після коми.
    """
    now = datetime.now()
    current_year = now.year
    
    # Розрахунок частки року, що залишилася (time-decay для поточного року)
    start_of_year = datetime(current_year, 1, 1)
    end_of_year = datetime(current_year, 12, 31)
    total_days = (end_of_year - start_of_year).days + 1
    remaining_days = max(1, (end_of_year - now).days + 1)
    time_fraction = remaining_days / total_days  # Наприклад, у листопаді це ~0.15 (15% року)
    
    y1 = str(current_year)
    y2 = str(current_year + 1)
    y3 = str(current_year + 2)
    
    # Базові річні ризики для повноцінного 365-денного циклу
    base_annual = {
        "russia_max": 5.00,
        "russia_partial": 12.00,
        "frozen": 22.00,
        "borders_1991": 7.00
    }
    
    forecasts = {}
    
    # 1. Поточний рік: помножуємо на залишок часу (чим ближче до 31 грудня, тим менші цифри)
    forecasts[y1] = {
        "russia_max": round(base_annual["russia_max"] * time_fraction, 2),
        "russia_partial": round(base_annual["russia_partial"] * time_fraction, 2),
        "frozen": round(base_annual["frozen"] * time_fraction, 2),
        "borders_1991": round(base_annual["borders_1991"] * time_fraction, 2)
    }
    
    # 2. Наступний рік: повний рік із кумулятивним ефектом виснаження
    multiplier_y2 = 1.35
    forecasts[y2] = {
        "russia_max": round(base_annual["russia_max"] * multiplier_y2, 2),
        "russia_partial": round(base_annual["russia_partial"] * multiplier_y2, 2),
        "frozen": round(base_annual["frozen"] * 1.20, 2),
        "borders_1991": round(base_annual["borders_1991"] * 1.40, 2)
    }
    
    # 3. Через рік: довгострокова перспектива з вищою варіативністю
    multiplier_y3 = 1.70
    forecasts[y3] = {
        "russia_max": round(base_annual["russia_max"] * multiplier_y3, 2),
        "russia_partial": round(base_annual["russia_partial"] * multiplier_y3, 2),
        "frozen": round(base_annual["frozen"] * 0.90, 2),  # Часткова трансформація конфлікту в інші форми
        "borders_1991": round(base_annual["borders_1991"] * 2.00, 2)
    }
    
    return forecasts

def main():
    print("🔄 Запуск повністю динамічного генератора прогнозу (Rolling Horizon)...")
    
    matrix_data = generate_dynamic_forecasts()
    
    output = {
        "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "metrics_source": "Autonomous Rolling-Horizon & Time-Decay Model",
        "forecasts": matrix_data
    }
    
    with open("war_forecast_data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
        
    print(f"✅ Успішно! Згенеровано прогноз для часового вікна: {list(matrix_data.keys())}")

if __name__ == "__main__":
    main()