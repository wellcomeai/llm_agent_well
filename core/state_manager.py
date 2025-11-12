"""
State Manager for Travel Agent
Manages conversation context and travel planning state across sessions
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List
from datetime import datetime
import json


@dataclass
class TravelContext:
    """Состояние планирования путешествия"""

    # Core travel information
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    passengers: int = 1

    # Additional preferences
    budget: Optional[str] = None
    travel_class: Optional[str] = None

    # Extracted entities history
    mentioned_cities: List[str] = field(default_factory=list)
    mentioned_dates: List[str] = field(default_factory=list)

    def is_complete_for_search(self) -> bool:
        """Проверка: есть ли всё для поиска рейсов"""
        return all([
            self.origin,
            self.destination,
            self.departure_date
        ])

    def is_complete_for_weather(self) -> bool:
        """Проверка: есть ли город для запроса погоды"""
        return self.destination is not None

    def get_missing_fields(self) -> List[str]:
        """Список недостающих полей для поиска рейсов"""
        missing = []
        if not self.origin:
            missing.append("город вылета")
        if not self.destination:
            missing.append("город назначения")
        if not self.departure_date:
            missing.append("дата вылета")
        return missing

    def update_from_dict(self, data: dict):
        """Обновление из извлеченного контекста"""
        if data.get('origin') and data['origin'] != 'null':
            self.origin = data['origin']
            if data['origin'] not in self.mentioned_cities:
                self.mentioned_cities.append(data['origin'])

        if data.get('destination') and data['destination'] != 'null':
            self.destination = data['destination']
            if data['destination'] not in self.mentioned_cities:
                self.mentioned_cities.append(data['destination'])

        if data.get('departure_date') and data['departure_date'] != 'null':
            self.departure_date = data['departure_date']
            if data['departure_date'] not in self.mentioned_dates:
                self.mentioned_dates.append(data['departure_date'])

        if data.get('return_date') and data['return_date'] != 'null':
            self.return_date = data['return_date']
            if data['return_date'] not in self.mentioned_dates:
                self.mentioned_dates.append(data['return_date'])

        if data.get('passengers'):
            try:
                self.passengers = int(data['passengers'])
            except (ValueError, TypeError):
                pass

        if data.get('budget'):
            self.budget = data['budget']

        if data.get('travel_class'):
            self.travel_class = data['travel_class']

    def to_dict(self) -> dict:
        """Сериализация в словарь"""
        return {
            'origin': self.origin,
            'destination': self.destination,
            'departure_date': self.departure_date,
            'return_date': self.return_date,
            'passengers': self.passengers,
            'budget': self.budget,
            'travel_class': self.travel_class,
            'mentioned_cities': self.mentioned_cities,
            'mentioned_dates': self.mentioned_dates
        }

    def get_summary(self) -> str:
        """Человеко-читаемое резюме состояния"""
        parts = []

        if self.origin and self.destination:
            parts.append(f"Маршрут: {self.origin} → {self.destination}")
        elif self.origin:
            parts.append(f"Вылет из: {self.origin}")
        elif self.destination:
            parts.append(f"Прилёт в: {self.destination}")

        if self.departure_date:
            parts.append(f"Дата: {self.departure_date}")

        if self.return_date:
            parts.append(f"Обратно: {self.return_date}")

        if self.passengers and self.passengers > 1:
            parts.append(f"Пассажиры: {self.passengers}")

        if self.budget:
            parts.append(f"Бюджет: {self.budget}")

        if self.travel_class:
            parts.append(f"Класс: {self.travel_class}")

        return ", ".join(parts) if parts else "Параметры не указаны"


class StateManager:
    """Управление состоянием сессий"""

    def __init__(self):
        self.states: Dict[str, TravelContext] = {}

    def get_state(self, session_id: str) -> TravelContext:
        """Получить состояние для сессии (создаёт новое если нет)"""
        if session_id not in self.states:
            self.states[session_id] = TravelContext()
        return self.states[session_id]

    def update_state(self, session_id: str, extracted: dict) -> TravelContext:
        """Обновить состояние из извлеченных данных"""
        state = self.get_state(session_id)
        state.update_from_dict(extracted)
        return state

    def clear_state(self, session_id: str):
        """Очистить состояние сессии"""
        if session_id in self.states:
            del self.states[session_id]

    def reset_travel_params(self, session_id: str):
        """Сбросить параметры путешествия, сохранив историю упоминаний"""
        state = self.get_state(session_id)
        mentioned_cities = state.mentioned_cities.copy()
        mentioned_dates = state.mentioned_dates.copy()

        # Создать новый контекст
        self.states[session_id] = TravelContext()
        self.states[session_id].mentioned_cities = mentioned_cities
        self.states[session_id].mentioned_dates = mentioned_dates

    def export_state(self, session_id: str) -> str:
        """Экспорт состояния в JSON"""
        state = self.get_state(session_id)
        return json.dumps(state.to_dict(), ensure_ascii=False, indent=2)

    def import_state(self, session_id: str, json_data: str):
        """Импорт состояния из JSON"""
        data = json.loads(json_data)
        state = self.get_state(session_id)
        state.update_from_dict(data)
