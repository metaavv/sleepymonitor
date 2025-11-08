import sqlite3
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_name: str):
        self.db_name = db_name
        self.init_db()

    def get_connection(self):
        """Получение соединения с базой данных"""
        return sqlite3.connect(self.db_name, detect_types=sqlite3.PARSE_DECLTYPES)

    def init_db(self):
        """Инициализация базы данных"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Таблица пользователей
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица дней (основные записи)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS days (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        date TEXT,
                        sleep_time TEXT,
                        wake_time TEXT,
                        total_sleep_minutes INTEGER,
                        no_sleep BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id),
                        UNIQUE(user_id, date)
                    )
                ''')
                
                # Таблица дополнительных снов (для дневных снов)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS additional_sleeps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        date TEXT,
                        sleep_time TEXT,
                        wake_time TEXT,
                        sleep_minutes INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Таблица симптомов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS symptoms (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        date TEXT,
                        symptom_text TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                conn.commit()
                logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")

    def add_user(self, user_id: int, username: str, first_name: str, last_name: str):
        """Добавление пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, username or "", first_name or "", last_name or ""))
                conn.commit()
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")

    def record_sleep(self, user_id: int, sleep_time: datetime, target_date: date = None) -> bool:
        """Запись времени засыпания"""
        try:
            if target_date is None:
                target_date = sleep_time.date()
            
            date_str = target_date.isoformat()
            sleep_time_str = sleep_time.isoformat()
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Проверяем существующую запись
                cursor.execute('''
                    SELECT sleep_time, wake_time, total_sleep_minutes FROM days 
                    WHERE user_id = ? AND date = ?
                ''', (user_id, date_str))
                
                existing = cursor.fetchone()
                
                if existing:
                    # Обновляем только время засыпания, сохраняем существующие данные
                    wake_time = existing[1] if existing[1] else None
                    total_sleep_minutes = existing[2] if existing[2] else None
                    
                    # Если есть время пробуждения, пересчитываем общее время сна
                    if wake_time:
                        wake_time_dt = datetime.fromisoformat(wake_time)
                        total_sleep_minutes = int((wake_time_dt - sleep_time).total_seconds() / 60)
                    
                    cursor.execute('''
                        UPDATE days 
                        SET sleep_time = ?, total_sleep_minutes = ?, updated_at = ?, no_sleep = FALSE
                        WHERE user_id = ? AND date = ?
                    ''', (sleep_time_str, total_sleep_minutes, datetime.now(), user_id, date_str))
                else:
                    # Создаем новую запись
                    cursor.execute('''
                        INSERT INTO days (user_id, date, sleep_time, updated_at, no_sleep)
                        VALUES (?, ?, ?, ?, FALSE)
                    ''', (user_id, date_str, sleep_time_str, datetime.now()))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error recording sleep for user {user_id}: {e}")
            return False

    def record_wake(self, user_id: int, wake_time: datetime, target_date: date = None) -> bool:
        """Запись времени пробуждения"""
        try:
            if target_date is None:
                target_date = wake_time.date()
            
            date_str = target_date.isoformat()
            wake_time_str = wake_time.isoformat()
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Проверяем существующую запись
                cursor.execute('''
                    SELECT sleep_time, wake_time, total_sleep_minutes FROM days 
                    WHERE user_id = ? AND date = ?
                ''', (user_id, date_str))
                
                existing = cursor.fetchone()
                
                total_sleep_minutes = 0
                
                if existing:
                    # Обновляем только время пробуждения, сохраняем существующие данные
                    sleep_time_str = existing[0] if existing[0] else None
                    
                    # Если есть время засыпания, пересчитываем общее время сна
                    if sleep_time_str:
                        sleep_time_dt = datetime.fromisoformat(sleep_time_str)
                        
                        # Корректно рассчитываем разницу, даже если сон переходит через полночь
                        if wake_time < sleep_time_dt:
                            # Если пробуждение раньше засыпания (сон через полночь)
                            # Добавляем 1 день к времени пробуждения для корректного расчета
                            wake_time_corrected = wake_time + timedelta(days=1)
                            total_sleep_minutes = int((wake_time_corrected - sleep_time_dt).total_seconds() / 60)
                        else:
                            # Обычный случай - сон в пределах одних суток
                            total_sleep_minutes = int((wake_time - sleep_time_dt).total_seconds() / 60)
                
                    cursor.execute('''
                        UPDATE days 
                        SET wake_time = ?, total_sleep_minutes = ?, updated_at = ?, no_sleep = FALSE
                        WHERE user_id = ? AND date = ?
                    ''', (wake_time_str, total_sleep_minutes, datetime.now(), user_id, date_str))
                else:
                    # Создаем новую запись только с временем пробуждения
                    cursor.execute('''
                        INSERT INTO days (user_id, date, wake_time, updated_at, no_sleep)
                        VALUES (?, ?, ?, ?, FALSE)
                    ''', (user_id, date_str, wake_time_str, datetime.now()))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error recording wake for user {user_id}: {e}")
            return False

    def record_no_sleep(self, user_id: int, target_date: date = None) -> bool:
        """Запись отметки 'не спал'"""
        try:
            if target_date is None:
                target_date = date.today()
            
            date_str = target_date.isoformat()
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO days (user_id, date, no_sleep, sleep_time, wake_time, total_sleep_minutes, updated_at)
                    VALUES (?, ?, TRUE, NULL, NULL, 0, ?)
                ''', (user_id, date_str, datetime.now()))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error recording no_sleep for user {user_id}: {e}")
            return False

    def add_additional_sleep(self, user_id: int, sleep_time: datetime, wake_time: datetime, target_date: date = None) -> bool:
        """Добавление дополнительного сна"""
        try:
            if target_date is None:
                target_date = sleep_time.date()
            
            date_str = target_date.isoformat()
            sleep_time_str = sleep_time.isoformat()
            wake_time_str = wake_time.isoformat()
            sleep_minutes = int((wake_time - sleep_time).total_seconds() / 60)
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO additional_sleeps (user_id, date, sleep_time, wake_time, sleep_minutes)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, date_str, sleep_time_str, wake_time_str, sleep_minutes))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding additional sleep for user {user_id}: {e}")
            return False

    def add_symptom(self, user_id: int, symptom_text: str, symptom_date: date = None) -> bool:
        """Добавление симптома"""
        try:
            if symptom_date is None:
                symptom_date = date.today()
            
            date_str = symptom_date.isoformat()
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO symptoms (user_id, date, symptom_text)
                    VALUES (?, ?, ?)
                ''', (user_id, date_str, symptom_text))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding symptom for user {user_id}: {e}")
            return False

    def get_day_summary(self, user_id: int, target_date: date) -> Dict:
        """Получение сводки за день"""
        try:
            date_str = target_date.isoformat()
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Получаем основные данные о сне
                cursor.execute('''
                    SELECT sleep_time, wake_time, total_sleep_minutes, no_sleep 
                    FROM days 
                    WHERE user_id = ? AND date = ?
                ''', (user_id, date_str))
                
                sleep_data = cursor.fetchone()
                
                # Получаем дополнительные сны
                cursor.execute('''
                    SELECT sleep_time, wake_time, sleep_minutes 
                    FROM additional_sleeps 
                    WHERE user_id = ? AND date = ?
                    ORDER BY sleep_time
                ''', (user_id, date_str))
                
                additional_sleeps = [{
                    'sleep_time': row[0],
                    'wake_time': row[1], 
                    'sleep_minutes': row[2]
                } for row in cursor.fetchall()]
                
                # Получаем симптомы
                cursor.execute('''
                    SELECT id, symptom_text 
                    FROM symptoms 
                    WHERE user_id = ? AND date = ?
                    ORDER BY created_at
                ''', (user_id, date_str))
                
                symptoms = [{'id': row[0], 'text': row[1]} for row in cursor.fetchall()]
                
                # Рассчитываем общее время сна (основной + дополнительные сны)
                total_sleep_all_minutes = 0
                main_sleep_minutes = sleep_data[2] if sleep_data and sleep_data[2] else 0
                
                for sleep in additional_sleeps:
                    total_sleep_all_minutes += sleep['sleep_minutes']
                
                total_sleep_all_minutes += main_sleep_minutes
                
                return {
                    'sleep_time': sleep_data[0] if sleep_data and sleep_data[0] else None,
                    'wake_time': sleep_data[1] if sleep_data and sleep_data[1] else None,
                    'total_sleep_minutes': sleep_data[2] if sleep_data else None,
                    'total_sleep_all_minutes': total_sleep_all_minutes,  # Основной + доп. сны
                    'no_sleep': bool(sleep_data[3]) if sleep_data else False,
                    'additional_sleeps': additional_sleeps,
                    'symptoms': symptoms
                }
        except Exception as e:
            logger.error(f"Error getting day summary for user {user_id}: {e}")
            return {
                'sleep_time': None, 
                'wake_time': None, 
                'total_sleep_minutes': None, 
                'total_sleep_all_minutes': 0,
                'no_sleep': False,
                'additional_sleeps': [],
                'symptoms': []
            }

    def check_existing_sleep_data(self, user_id: int, target_date: date) -> Dict:
        """Проверка существующих данных о сне за день"""
        try:
            date_str = target_date.isoformat()
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT sleep_time, wake_time, total_sleep_minutes, no_sleep 
                    FROM days 
                    WHERE user_id = ? AND date = ?
                ''', (user_id, date_str))
                
                data = cursor.fetchone()
                
                if data:
                    return {
                        'exists': True,
                        'sleep_time': data[0],
                        'wake_time': data[1],
                        'total_sleep_minutes': data[2],
                        'no_sleep': bool(data[3])
                    }
                else:
                    return {'exists': False}
                    
        except Exception as e:
            logger.error(f"Error checking existing sleep data for user {user_id}: {e}")
            return {'exists': False}

    def get_user_days(self, user_id: int, limit: int = 30) -> List[Tuple[date, bool]]:
        """Получение списка дней пользователя с информацией о наличии данных"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Находим все дни где есть ЛЮБЫЕ данные
                cursor.execute('''
                    SELECT DISTINCT date FROM (
                        SELECT date FROM days WHERE user_id = ? 
                        UNION 
                        SELECT date FROM additional_sleeps WHERE user_id = ?
                        UNION
                        SELECT date FROM symptoms WHERE user_id = ?
                    ) 
                    ORDER BY date DESC 
                    LIMIT ?
                ''', (user_id, user_id, user_id, limit))
                
                days_with_data = [date.fromisoformat(row[0]) for row in cursor.fetchall()]
                
                # Теперь проверяем каждый день на наличие основных данных
                result = []
                for day_date in days_with_data:
                    date_str = day_date.isoformat()
                    
                    # Проверяем есть ли основные данные в days
                    cursor.execute('''
                        SELECT COUNT(*) FROM days 
                        WHERE user_id = ? AND date = ? 
                        AND (sleep_time IS NOT NULL OR wake_time IS NOT NULL OR no_sleep = TRUE)
                    ''', (user_id, date_str))
                    
                    has_main_data = cursor.fetchone()[0] > 0
                    result.append((day_date, has_main_data))
                
                return result
        except Exception as e:
            logger.error(f"Error getting user days for user {user_id}: {e}")
            return []

    def get_recent_days(self, user_id: int, days_count: int = 3) -> List[Dict]:
        """Получение данных за последние N дней"""
        try:
            recent_days = []
            
            for i in range(days_count):
                target_date = date.today() - timedelta(days=i)
                summary = self.get_day_summary(user_id, target_date)
                recent_days.append({
                    'date': target_date,
                    'summary': summary
                })
            
            return recent_days
        except Exception as e:
            logger.error(f"Error getting recent days for user {user_id}: {e}")
            return []

    def delete_day(self, user_id: int, target_date: date) -> bool:
        """Удаление всех данных за день"""
        try:
            date_str = target_date.isoformat()
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Удаляем основные данные о сне
                cursor.execute('DELETE FROM days WHERE user_id = ? AND date = ?', (user_id, date_str))
                
                # Удаляем дополнительные сны
                cursor.execute('DELETE FROM additional_sleeps WHERE user_id = ? AND date = ?', (user_id, date_str))
                
                # Удаляем симптомы
                cursor.execute('DELETE FROM symptoms WHERE user_id = ? AND date = ?', (user_id, date_str))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error deleting day for user {user_id}: {e}")
            return False

    def delete_symptom(self, symptom_id: int) -> bool:
        """Удаление симптома"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM symptoms WHERE id = ?', (symptom_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error deleting symptom {symptom_id}: {e}")
            return False

    def delete_additional_sleep(self, sleep_id: int) -> bool:
        """Удаление дополнительного сна"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM additional_sleeps WHERE id = ?', (sleep_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error deleting additional sleep {sleep_id}: {e}")
            return False