import os
import time
import logging
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot, apihelper


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

TOKEN_NAMES = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    for i, token in enumerate((
        PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    )):
        if not token:
            logging.critical(
                'Отсутствует обязательная переменная окружения: '
                f'{TOKEN_NAMES[i]}. Программа принудительно остановлена.'
            )
            return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message
        )
        logging.debug('Сообщение успешно отправлено в Телеграм.')
    except apihelper.ApiException as error:
        logging.error(
            f'Возникла ошибка - {error} при отправке сообщения в Телеграм.'
        )

    return True


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    try:
        response = requests.get(
            url=ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except requests.RequestException as error:
        raise ConnectionError(
            f'Возникла ошибка - {error} во время запроса к сервису {ENDPOINT}.'
        )

    if response.status_code != HTTPStatus.OK:
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            code_error = response.json().get('code')
            message_error = response.json().get('message')
            raise ConnectionError(
                'Сервис недоступен. '
                f'Код ошибки сервиса: {code_error} - {message_error} '
                f'Код статуса запроса: {response.status_code}'
            )
        elif response.status_code == HTTPStatus.BAD_REQUEST:
            code_error = response.json().get('code')
            message_error = response.json().get('error').get('error')
            raise ConnectionError(
                'Сервис недоступен. '
                f'Код ошибки сервиса: {code_error} - {message_error}. '
                f'Код статуса запроса: {response.status_code}'
            )
        else:
            raise ConnectionError(
                'Сервис недоступен. '
                f'Код статуса запроса: {response.status_code}'
            )

    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(
            'Полученные данные от сервиса должны быть словарём.'
        )
    if 'homeworks' not in response:
        raise KeyError(
            'В полученном словаре нет ключа "homeworks".'
        )
    if not isinstance(response.get('homeworks'), list):
        raise TypeError(
            'Значение ключа "homeworks" должно быть списком.'
        )
    if 'current_date' not in response:
        raise KeyError(
            'В полученном словаре нет ключа "current_date".'
        )
    if not isinstance(response.get('current_date'), int):
        raise TypeError(
            'Значение ключа "current_date" должно быть целочисленным.'
        )

    return response.get('homeworks'), response.get('current_date')


def parse_status(homework):
    """Извлекает статус из информации о конкретной домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError(
            'В списке "homeworks" нет ключа "homework_name".'
        )
    if 'status' not in homework:
        raise KeyError(
            'В списке "homeworks" нет ключа "status".'
        )
    if homework.get('status') not in HOMEWORK_VERDICTS:
        raise ValueError(
            'В списке "homeworks" неизвестный "status".'
        )
    homework_name = homework.get('homework_name')
    verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        exit()

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    previous_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            homework, timestamp = check_response(response)
            if homework:
                message_to_telegram = parse_status(homework[0])
                if message_to_telegram is not previous_message:
                    if send_message(bot, message_to_telegram):
                        previous_message = message_to_telegram
            else:
                logging.debug('Статус домашки не изменился.')

        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            logging.error(error_message)
            if error_message is not previous_message:
                if send_message(bot, error_message):
                    previous_message = error_message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        filename='homework.log',
        filemode='w',
        format='%(asctime)s, %(levelname)s, %(message)s, %(funcName)s',
        encoding='utf-8'
    )
    main()
