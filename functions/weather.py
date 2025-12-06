"""
Weather function using wttr.in API.
Provides current weather information for a given city.
"""

import requests
from typing import Dict, Any


def get_weather(city: str) -> Dict[str, Any]:
    """
    Получает текущую погоду для указанного города.

    Args:
        city: Название города на английском (например, "Paris", "London", "Amsterdam")

    Returns:
        dict: Словарь с информацией о погоде:
            {
                "success": bool,
                "city": str,
                "temperature_c": str,
                "temperature_f": str,
                "description": str,
                "humidity": str,
                "wind_kph": str,
                "feels_like_c": str,
                "error": str (опционально, если произошла ошибка)
            }

    Example:
        >>> result = get_weather("Paris")
        >>> print(result)
        {
            "success": True,
            "city": "Paris",
            "temperature_c": "15",
            "temperature_f": "59",
            "description": "Partly cloudy",
            "humidity": "65%",
            "wind_kph": "12",
            "feels_like_c": "14"
        }
    """
    try:
        # wttr.in API endpoint - формат JSON
        # ?format=j1 возвращает подробный JSON
        url = f"https://wttr.in/{city}?format=j1"

        # Делаем запрос с таймаутом
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        # Извлекаем текущую погоду
        current = data.get("current_condition", [{}])[0]

        # Формируем ответ
        weather_info = {
            "success": True,
            "city": city,
            "temperature_c": current.get("temp_C", "N/A"),
            "temperature_f": current.get("temp_F", "N/A"),
            "description": current.get("weatherDesc", [{}])[0].get("value", "N/A"),
            "humidity": current.get("humidity", "N/A"),
            "wind_kph": current.get("windspeedKmph", "N/A"),
            "wind_mph": current.get("windspeedMiles", "N/A"),
            "feels_like_c": current.get("FeelsLikeC", "N/A"),
            "feels_like_f": current.get("FeelsLikeF", "N/A"),
            "precipitation_mm": current.get("precipMM", "N/A"),
            "cloud_cover": current.get("cloudcover", "N/A"),
        }

        return weather_info

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "city": city,
            "error": f"Timeout error: wttr.in API не ответил вовремя для города {city}"
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "city": city,
            "error": f"HTTP error при запросе погоды для {city}: {str(e)}"
        }
    except (KeyError, IndexError, ValueError) as e:
        return {
            "success": False,
            "city": city,
            "error": f"Ошибка парсинга данных погоды для {city}: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "city": city,
            "error": f"Неожиданная ошибка при получении погоды для {city}: {str(e)}"
        }


# OpenAPI-like metadata для Google ADK
get_weather.metadata = {
    "name": "get_weather",
    "description": "Получает текущую погоду для указанного города используя wttr.in API. Возвращает температуру, описание, влажность, ветер и другие метеоданные.",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "Название города на английском языке (например: Paris, London, Amsterdam, Tokyo)"
            }
        },
        "required": ["city"]
    }
}


# ============================================================================
# LANGCHAIN TOOL WRAPPER
# ============================================================================

from langchain.tools import tool as langchain_tool

@langchain_tool
def get_weather_tool(city: str) -> str:
    """
    Получает текущую погоду для указанного города.

    Args:
        city: Название города на английском (например: Paris, London, Amsterdam)

    Returns:
        JSON строка с информацией о погоде: температура, описание, влажность, ветер
    """
    import json
    result = get_weather(city)
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    # Тестирование функции
    print("Testing get_weather function...")
    print("\n1. Testing Paris:")
    result = get_weather("Paris")
    print(result)

    print("\n2. Testing London:")
    result = get_weather("London")
    print(result)

    print("\n3. Testing invalid city:")
    result = get_weather("InvalidCityName123")
    print(result)

    print("\n4. Testing LangChain tool wrapper:")
    result = get_weather_tool.invoke({"city": "Tokyo"})
    print(result)
