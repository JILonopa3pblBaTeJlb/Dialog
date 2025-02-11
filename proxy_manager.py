import requests
from bs4 import BeautifulSoup
import time
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# URL-адреса для получения списков прокси
PROXY_URL_SSL = 'https://www.sslproxies.org/'
PROXY_URL_FREE = 'https://free-proxy-list.net/'
PROXY_URL_PROXY_LIST_DOWNLOAD = 'https://www.proxy-list.download/HTTPS'

# Файл для хранения рабочего прокси
PROXY_FILE = 'proxy.txt'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def fetch_proxies_ssl():
    """Получаем список прокси с сайта sslproxies.org."""
    try:
        response = requests.get(PROXY_URL_SSL)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        proxy_table = soup.find(id='proxylisttable') or soup.find('table', class_='table table-striped table-bordered')
        
        if proxy_table:
            proxy_list = []
            rows = proxy_table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) > 1:
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    proxy = f"{ip}:{port}"
                    proxy_list.append(proxy)
            return proxy_list
        else:
            logging.error("Не удалось найти таблицу с прокси на sslproxies.org.")
            return []
    except requests.RequestException as e:
        logging.error(f"Ошибка при получении списка прокси с sslproxies.org: {e}")
        return []

def fetch_proxies_free():
    """Получаем список прокси с сайта free-proxy-list.net."""
    try:
        response = requests.get(PROXY_URL_FREE)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        proxy_table = soup.find('table', {'class': 'table table-striped table-bordered'})
        
        if proxy_table:
            proxy_list = []
            rows = proxy_table.find_all('tr')[1:]  # Пропускаем заголовок таблицы
            for row in rows:
                cols = row.find_all('td')
                ip = cols[0].text.strip()
                port = cols[1].text.strip()
                proxy = f"{ip}:{port}"
                proxy_list.append(proxy)
            return proxy_list
        else:
            logging.error("Не удалось найти таблицу с прокси на free-proxy-list.net.")
            return []
    except requests.RequestException as e:
        logging.error(f"Ошибка при получении списка прокси с free-proxy-list.net: {e}")
        return []

def fetch_proxies_proxy_list_download():
    """Получаем список прокси с сайта proxy-list.download."""
    try:
        response = requests.get(PROXY_URL_PROXY_LIST_DOWNLOAD)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        proxy_table = soup.find('table', {'id': 'example1'})
        
        if proxy_table:
            proxy_list = []
            rows = proxy_table.find('tbody').find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                ip = cols[0].text.strip()
                port = cols[1].text.strip()
                proxy = f"{ip}:{port}"
                proxy_list.append(proxy)
            return proxy_list
        else:
            logging.error("Не удалось найти таблицу с прокси на proxy-list.download.")
            return []
    except requests.RequestException as e:
        logging.error(f"Ошибка при получении списка прокси с proxy-list.download: {e}")
        return []

def is_https_proxy(proxy, timeout_seconds=3):
    """Проверяем, поддерживает ли предоставленный прокси HTTPS и соответствует ли времени отклика."""
    proxies = {
        'http': f'http://{proxy}',
        'https': f'http://{proxy}',
    }
    
    test_urls = ['https://api.ipify.org', 'https://www.google.com']
    
    for test_url in test_urls:
        try:
            start_time = time.time()
            logging.debug(f"Тестируем прокси: {proxy} на {test_url}")
            response = requests.get(test_url, proxies=proxies, timeout=timeout_seconds)
            end_time = time.time()
            response_time = end_time - start_time
            
            if response.status_code == 200 and response_time <= timeout_seconds:
                logging.info(f"Прокси прошел проверку на {test_url}: {proxy}, Время отклика: {response_time:.2f} секунд")
            else:
                logging.error(f"Прокси не подходит для {test_url}: {proxy}, Статус: {response.status_code}, Время отклика: {response_time:.2f} секунд")
                return False
        
        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка при тестировании прокси на {test_url}: {proxy} - {str(e)}")
            return False

    return True

def save_working_proxy(proxy):
    """Сохраняем рабочий прокси в файл."""
    try:
        with open(PROXY_FILE, 'w') as file:
            file.write(proxy)
    except IOError as e:
        logging.error(f"Ошибка при сохранении прокси в файл: {e}")

def load_previous_proxy():
    """Загружаем предыдущий сохраненный прокси, если он существует."""
    if os.path.exists(PROXY_FILE):
        try:
            with open(PROXY_FILE, 'r') as file:
                return file.read().strip()
        except IOError as e:
            logging.error(f"Ошибка при чтении файла с прокси: {e}")
    return None

def check_previous_proxy(proxy):
    """Проверяем предыдущий прокси запросом на Google."""
    if proxy:
        logging.info(f"Проверяем предыдущий прокси: {proxy}")
        return is_https_proxy(proxy, timeout_seconds=4)
    return False

def fetch_proxies():
    """Получаем список прокси с всех доступных сайтов."""
    proxies_ssl = fetch_proxies_ssl()
    proxies_free = fetch_proxies_free()
    proxies_download = fetch_proxies_proxy_list_download()
    return proxies_ssl + proxies_free + proxies_download

def main():
    """Основная функция для получения и сохранения рабочего прокси."""
    logging.info("Получаем список прокси...")
    previous_proxy = load_previous_proxy()

    while True:
        if previous_proxy and check_previous_proxy(previous_proxy):
            logging.info(f"Предыдущий прокси все еще рабочий: {previous_proxy}. Пропускаем поиск нового.")
        else:
            logging.info("Поиск нового рабочего прокси...")
            proxies = fetch_proxies()
            
            if not proxies:
                logging.error("Список прокси пуст, пробуем снова через 60 секунд...")
                time.sleep(60)
                continue
            
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_proxy = {executor.submit(is_https_proxy, proxy): proxy for proxy in proxies}
                for future in as_completed(future_to_proxy):
                    proxy = future_to_proxy[future]
                    try:
                        if future.result():
                            if proxy == previous_proxy:
                                logging.info(f"Найденный прокси совпадает с предыдущим: {proxy}. Пропускаем...")
                                continue
                            logging.info(f"Рабочий HTTPS прокси найден: {proxy}")
                            save_working_proxy(proxy)
                            previous_proxy = proxy
                            break
                    except Exception as e:
                        logging.error(f"Ошибка в потоке проверки прокси: {e}")
        
        logging.info("Ждем перед следующим циклом проверки...")
        time.sleep(60)

if __name__ == '__main__':
    main()
