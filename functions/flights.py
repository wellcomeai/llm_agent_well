"""
Flights search function with mock data.
For MVP purposes, returns simulated flight data.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import random


def search_flights(
    from_city: str,
    to_city: str,
    date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ищет рейсы между двумя городами на указанную дату.

    MVP версия: возвращает mock данные (2-3 симуляционных рейса).
    В production версии здесь будет интеграция с реальным API (например, Amadeus, Skyscanner).

    Args:
        from_city: Город вылета (например, "Amsterdam", "Paris")
        to_city: Город прилета (например, "Paris", "London")
        date: Дата в формате YYYY-MM-DD. Если не указана, используется завтра.

    Returns:
        dict: Словарь с информацией о рейсах:
            {
                "success": bool,
                "from": str,
                "to": str,
                "date": str,
                "flights": [
                    {
                        "flight_number": str,
                        "airline": str,
                        "departure": str,
                        "arrival": str,
                        "price_eur": int,
                        "duration_minutes": int,
                        "aircraft": str,
                        "stops": int
                    },
                    ...
                ],
                "error": str (опционально)
            }

    Example:
        >>> result = search_flights("Amsterdam", "Paris", "2025-01-16")
        >>> print(result)
        {
            "success": True,
            "from": "Amsterdam",
            "to": "Paris",
            "date": "2025-01-16",
            "flights": [...]
        }
    """
    try:
        # Если дата не указана, используем завтра
        if date is None:
            tomorrow = datetime.now() + timedelta(days=1)
            date = tomorrow.strftime("%Y-%m-%d")
        else:
            # Валидация формата даты
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return {
                    "success": False,
                    "from": from_city,
                    "to": to_city,
                    "error": f"Неверный формат даты: {date}. Используйте YYYY-MM-DD"
                }

        # Mock данные: популярные авиакомпании и самолеты
        airlines_data = {
            "KLM": {"aircraft": ["Boeing 737", "Airbus A320"], "base_price": 80},
            "Air France": {"aircraft": ["Airbus A320", "Airbus A321"], "base_price": 90},
            "EasyJet": {"aircraft": ["Airbus A319", "Airbus A320"], "base_price": 60},
            "Ryanair": {"aircraft": ["Boeing 737-800"], "base_price": 50},
            "Lufthansa": {"aircraft": ["Airbus A320", "Boeing 737"], "base_price": 95},
        }

        # Генерируем 2-3 рейса
        num_flights = random.randint(2, 3)
        flights = []

        # Базовые времена вылета
        departure_times = ["06:30", "10:00", "14:30", "18:00", "21:30"]
        selected_times = random.sample(departure_times, num_flights)

        for i, dep_time in enumerate(selected_times):
            airline = random.choice(list(airlines_data.keys()))
            airline_info = airlines_data[airline]

            # Генерация номера рейса
            flight_number = f"{airline[:2].upper()}{random.randint(1000, 9999)}"

            # Расчет времени полета (например, 1-3 часа)
            duration_minutes = random.randint(60, 180)

            # Расчет времени прилета
            dep_datetime = datetime.strptime(f"{date} {dep_time}", "%Y-%m-%d %H:%M")
            arr_datetime = dep_datetime + timedelta(minutes=duration_minutes)

            # Цена с вариацией
            base_price = airline_info["base_price"]
            price_variation = random.randint(-20, 40)
            price = base_price + price_variation

            # Тип самолета
            aircraft = random.choice(airline_info["aircraft"])

            # Количество остановок (в основном прямые рейсы)
            stops = 0 if random.random() < 0.8 else 1

            flight = {
                "flight_number": flight_number,
                "airline": airline,
                "departure": dep_datetime.strftime("%Y-%m-%d %H:%M"),
                "arrival": arr_datetime.strftime("%Y-%m-%d %H:%M"),
                "price_eur": price,
                "duration_minutes": duration_minutes,
                "aircraft": aircraft,
                "stops": stops,
                "available_seats": random.randint(10, 150)
            }

            flights.append(flight)

        # Сортировка по времени вылета
        flights.sort(key=lambda x: x["departure"])

        return {
            "success": True,
            "from": from_city,
            "to": to_city,
            "date": date,
            "flights_count": len(flights),
            "flights": flights,
            "note": "MVP mode: это симулированные данные. В production будет интеграция с реальным API."
        }

    except Exception as e:
        return {
            "success": False,
            "from": from_city,
            "to": to_city,
            "error": f"Ошибка при поиске рейсов: {str(e)}"
        }


# OpenAPI-like metadata для Google ADK
search_flights.metadata = {
    "name": "search_flights",
    "description": "Ищет доступные рейсы между двумя городами на указанную дату. Возвращает информацию о рейсах: номер, авиакомпания, время вылета/прилета, цена, продолжительность. MVP версия возвращает mock данные.",
    "parameters": {
        "type": "object",
        "properties": {
            "from_city": {
                "type": "string",
                "description": "Город вылета (например: Amsterdam, London, Paris)"
            },
            "to_city": {
                "type": "string",
                "description": "Город прилета (например: Paris, Berlin, Rome)"
            },
            "date": {
                "type": "string",
                "description": "Дата вылета в формате YYYY-MM-DD. Если не указана, используется завтра.",
                "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
            }
        },
        "required": ["from_city", "to_city"]
    }
}


if __name__ == "__main__":
    # Тестирование функции
    print("Testing search_flights function...")

    print("\n1. Testing Amsterdam -> Paris (tomorrow):")
    result = search_flights("Amsterdam", "Paris")
    print(result)

    print("\n2. Testing London -> Berlin (specific date):")
    result = search_flights("London", "Berlin", "2025-01-20")
    print(result)

    print("\n3. Testing with invalid date format:")
    result = search_flights("Paris", "Rome", "2025/01/20")
    print(result)
