"""
Context Extractor for Travel Agent
Extracts entities (cities, dates, passengers) from conversation history
"""

import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from langchain_openai import ChatOpenAI


class ContextExtractor:
    """Извлекает сущности из истории диалога"""

    # Месяцы для парсинга дат
    MONTHS_RU = {
        'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
        'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
        'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12',
        'январь': '01', 'февраль': '02', 'март': '03', 'апрель': '04',
        'май': '05', 'июнь': '06', 'июль': '07', 'август': '08',
        'сентябрь': '09', 'октябрь': '10', 'ноябрь': '11', 'декабрь': '12'
    }

    # Известные города (для быстрого поиска)
    KNOWN_CITIES = [
        'москва', 'москвы', 'петербург', 'санкт-петербург', 'питер', 'питера',
        'париж', 'парижа', 'лондон', 'лондона', 'берлин', 'берлина',
        'токио', 'нью-йорк', 'дубай', 'дубая', 'стамбул', 'стамбула',
        'рим', 'рима', 'барселона', 'барселоны', 'амстердам', 'амстердама',
        'прага', 'праги', 'вена', 'вены', 'будапешт', 'будапешта',
        'тайланд', 'бангкок', 'пхукет'
    ]

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    def extract_context(
        self,
        chat_history: List[Any],
        current_query: str
    ) -> Dict[str, Any]:
        """
        Извлекает контекст из истории диалога и текущего запроса

        Returns:
            Dict with keys: origin, destination, departure_date, return_date, passengers
        """

        # 1. Быстрая эвристическая экстракция
        heuristic_result = self._heuristic_extraction(chat_history, current_query)

        # 2. Если эвристика не нашла всё - используем LLM
        if not self._is_complete(heuristic_result):
            llm_result = self._llm_extraction(chat_history, current_query)

            # Объединяем результаты (приоритет у LLM)
            for key, value in llm_result.items():
                if value and value != 'null':
                    heuristic_result[key] = value

        return heuristic_result

    def _heuristic_extraction(
        self,
        chat_history: List[Any],
        current_query: str
    ) -> Dict[str, Any]:
        """Быстрая эвристическая экстракция без LLM"""

        result = {
            'origin': None,
            'destination': None,
            'departure_date': None,
            'return_date': None,
            'passengers': None
        }

        # Собрать все сообщения в один текст
        full_text = current_query + " "

        if isinstance(chat_history, list):
            for msg in chat_history:
                if isinstance(msg, dict):
                    content = msg.get('content', '')
                elif hasattr(msg, 'content'):
                    content = msg.content
                else:
                    content = str(msg)

                full_text += content + " "

        full_text = full_text.lower()

        # 1. Извлечь города
        cities_found = []
        for city in self.KNOWN_CITIES:
            if city in full_text:
                # Нормализовать название
                normalized = self._normalize_city_name(city)
                if normalized not in cities_found:
                    cities_found.append(normalized)

        # Первый город - origin, второй - destination
        if len(cities_found) >= 1:
            result['destination'] = cities_found[0]  # Чаще спрашивают "куда"
        if len(cities_found) >= 2:
            result['origin'] = cities_found[1]

        # Попытка найти "из X в Y"
        from_to_pattern = r'из\s+([а-яё\-]+)\s+в\s+([а-яё\-]+)'
        match = re.search(from_to_pattern, full_text)
        if match:
            result['origin'] = self._normalize_city_name(match.group(1))
            result['destination'] = self._normalize_city_name(match.group(2))

        # 2. Извлечь даты
        dates_found = self._extract_dates(full_text)
        if len(dates_found) >= 1:
            result['departure_date'] = dates_found[0]
        if len(dates_found) >= 2:
            result['return_date'] = dates_found[1]

        # 3. Извлечь количество пассажиров
        passengers_pattern = r'(\d+)\s+(человек|пассажир|билет)'
        match = re.search(passengers_pattern, full_text)
        if match:
            result['passengers'] = int(match.group(1))

        return result

    def _extract_dates(self, text: str) -> List[str]:
        """Извлечь даты из текста"""
        dates = []
        current_year = datetime.now().year

        # Паттерн: "20 ноября", "15 января 2024"
        date_pattern = r'(\d{1,2})\s+(' + '|'.join(self.MONTHS_RU.keys()) + r')(?:\s+(\d{4}))?'

        for match in re.finditer(date_pattern, text):
            day = match.group(1).zfill(2)
            month = self.MONTHS_RU[match.group(2)]
            year = match.group(3) if match.group(3) else str(current_year)

            date_str = f"{year}-{month}-{day}"

            # Валидация даты
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
                if date_str not in dates:
                    dates.append(date_str)
            except ValueError:
                continue

        # Паттерн: ISO формат "2024-11-20"
        iso_pattern = r'(\d{4})-(\d{2})-(\d{2})'
        for match in re.finditer(iso_pattern, text):
            date_str = match.group(0)
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
                if date_str not in dates:
                    dates.append(date_str)
            except ValueError:
                continue

        return dates

    def _normalize_city_name(self, city: str) -> str:
        """Нормализовать название города"""
        city = city.lower().strip()

        # Маппинг вариантов на канонические названия
        city_map = {
            'москва': 'Москва', 'москвы': 'Москва',
            'петербург': 'Санкт-Петербург', 'санкт-петербург': 'Санкт-Петербург',
            'питер': 'Санкт-Петербург', 'питера': 'Санкт-Петербург',
            'париж': 'Париж', 'парижа': 'Париж',
            'лондон': 'Лондон', 'лондона': 'Лондон',
            'берлин': 'Берлин', 'берлина': 'Берлин',
            'токио': 'Токио',
            'дубай': 'Дубай', 'дубая': 'Дубай',
            'стамбул': 'Стамбул', 'стамбула': 'Стамбул',
            'рим': 'Рим', 'рима': 'Рим',
            'барселона': 'Барселона', 'барселоны': 'Барселона',
            'амстердам': 'Амстердам', 'амстердама': 'Амстердам',
            'прага': 'Прага', 'праги': 'Прага',
            'вена': 'Вена', 'вены': 'Вена',
            'будапешт': 'Будапешт', 'будапешта': 'Будапешт',
            'тайланд': 'Тайланд',
            'бангкок': 'Бангкок',
            'пхукет': 'Пхукет'
        }

        return city_map.get(city, city.capitalize())

    def _is_complete(self, result: Dict[str, Any]) -> bool:
        """Проверить, извлечены ли основные данные"""
        return bool(result.get('origin') and result.get('destination'))

    def _llm_extraction(
        self,
        chat_history: List[Any],
        current_query: str
    ) -> Dict[str, Any]:
        """LLM-based extraction для сложных случаев"""

        # Форматировать историю
        history_text = ""
        if isinstance(chat_history, list):
            for i, msg in enumerate(chat_history[-10:]):  # Последние 10 сообщений
                if isinstance(msg, dict):
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                elif hasattr(msg, 'type'):
                    role = msg.type
                    content = msg.content
                else:
                    role = 'unknown'
                    content = str(msg)

                history_text += f"{role}: {content}\n"

        # Получить текущий год для промпта
        current_year = datetime.now().year
        current_date = datetime.now().strftime('%Y-%m-%d')

        prompt = f"""Проанализируй историю диалога и текущий запрос пользователя.
Извлеки информацию о путешествии.

ТЕКУЩАЯ ДАТА: {current_date}

История диалога:
{history_text}

Текущий запрос: {current_query}

Верни ТОЛЬКО валидный JSON в следующем формате:
{{
    "origin": "город вылета или null",
    "destination": "город прилёта или null",
    "departure_date": "дата в формате YYYY-MM-DD или null",
    "return_date": "дата возврата в формате YYYY-MM-DD или null",
    "passengers": число или null
}}

ВАЖНЫЕ ПРАВИЛА:
1. Извлекай информацию из ВСЕЙ истории, не только из последнего сообщения
2. Если информация не найдена - используй null
3. Даты ОБЯЗАТЕЛЬНО в формате YYYY-MM-DD
4. Если год не указан явно - используй текущий год {current_year}
5. Ответ ДОЛЖЕН быть валидным JSON без дополнительного текста
6. Если пользователь говорит "в Париж" или "в Тайланд" - это destination
7. Если пользователь говорит "из Москвы" - это origin
8. Если дата в прошлом - используй следующий год
"""

        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()

            # Извлечь JSON из ответа (на случай если LLM добавила текст)
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)

            result = json.loads(content)

            # Валидация и очистка
            for key in ['origin', 'destination', 'departure_date', 'return_date']:
                if result.get(key) == 'null' or not result.get(key):
                    result[key] = None

            if result.get('passengers') == 'null' or not result.get('passengers'):
                result['passengers'] = None

            # ИСПРАВЛЕНО: Валидация дат - если год в прошлом, заменить на текущий или следующий
            current_year = datetime.now().year
            current_date_obj = datetime.now()

            for date_field in ['departure_date', 'return_date']:
                if result.get(date_field):
                    try:
                        date_obj = datetime.strptime(result[date_field], '%Y-%m-%d')
                        
                        # Если дата в прошлом
                        if date_obj < current_date_obj:
                            # Если месяц уже прошел в этом году - берем следующий год
                            if date_obj.month < current_date_obj.month:
                                new_year = current_year + 1
                            else:
                                new_year = current_year
                            
                            result[date_field] = f"{new_year}-{date_obj.month:02d}-{date_obj.day:02d}"
                            print(f"Date corrected: {date_obj.date()} -> {result[date_field]}")
                    except Exception as e:
                        print(f"Date validation error for {date_field}: {e}")
                        pass

            return result

        except Exception as e:
            print(f"LLM extraction error: {e}")
            return {
                'origin': None,
                'destination': None,
                'departure_date': None,
                'return_date': None,
                'passengers': None
            }
