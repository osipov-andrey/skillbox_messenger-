import asyncio
from asyncio import transports
from typing import Optional
import sqlite3

"""
Серверное приложение для соединений
"""


class HistoryStorage:
    """ Для хранения сообщений используем встроенную БД """

    def __init__(self):
        self.storage = sqlite3.connect(":memory:")
        self._create_table()

    def _create_table(self):
        """ Создаем таблицу в памяти при создании хранилища """

        self.storage.execute('CREATE TABLE "messages" '
                             '(id INTEGER PRIMARY KEY AUTOINCREMENT, login, message)')

    def save_message(self, login: str, message: str):
        self.storage.execute(f'INSERT INTO messages(login, message) '
                             f'VALUES ("{login}", "{message}")')

    def take_history(self, limit: int = 10):
        messages = self.storage.execute(
            f'SELECT login, message FROM messages ORDER BY id DESC LIMIT {limit}'
        ).fetchall()
        return messages[::-1]


history = HistoryStorage()


class ClientProtocol(asyncio.Protocol):

    login: str
    server: 'Server'
    transport: transports.Transport

    def __init__(self, server: 'Server'):
        self.server = server
        self.login = None

    def data_received(self, data: bytes) -> None:
        decoded = data.decode()
        print(decoded)

        if self.login is None:
            # login:User

            if decoded.startswith("login:"):
                login = decoded.replace("login:", "").replace("\r\n", "")

                if not self._existing_login(login):  # Проверим, если ли клиент с таким именем в списке сервера
                    self.login = login  # Если нет: присваиваем текущему клиенту имя ...
                    self.transport.write(
                        f"Hello, {self.login}".encode()
                    )
                    self.send_history()  # ...отправляем текущему клиенту историю сообщений.
                else:
                    self.transport.write(  # Если есть - пишем соотв. сообщение...
                        f"Логин \"{login}\" занят, попробуйте другой".encode()
                    )
                    self.server.clients.remove(self)  # ... удаляем клиента из списка сервера ...
                    self.transport.close()  # ... отключаем соединение от сервера.

        else:
            self.send_message(decoded)

    def send_message(self, message):
        format_string = f"<{self.login.strip()}>: {message}"
        history.save_message(self.login, message)  # Добавляем сообщение в историю
        encoded = format_string.encode()

        for client in self.server.clients:
            if client.login != self.login:
                client.transport.write(encoded)

    def connection_made(self, transport: transports.Transport) -> None:
        self.transport = transport
        print("Connection made")
        self.server.clients.append(self)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        self.server.clients.remove(self)
        print("Connection lost")

    def _existing_login(self, login):
        """
        Можно реализовать хранение авторизованных клиентов в словаре - 'имя': 'клиент',
        тогда проверка была бы проще
        """
        existing_login = list(filter(lambda x: x.login == login, self.server.clients))
        return bool(existing_login)

    def send_history(self, needed_history=10):
        """
        Берем последние 10 или менее сообщений из истории и отправляем самому себе
        """
        his = history.take_history(needed_history)
        print(his)
        for message in his:
            message_to_sent = f"<{message[0].strip()}>: {message[1]}"
            self.transport.write(('\n\r' + message_to_sent).encode())


class Server:
    clients: list

    def __init__(self):
        self.clients = []

    def create_client_protocol(self):
        return ClientProtocol(self)

    async def start(self):
        loop = asyncio.get_running_loop()

        coroutine = await loop.create_server(
            self.create_client_protocol,
            "127.0.0.1",
            8888,
        )

        print('Сервер запущен ...')

        await coroutine.serve_forever()


process = Server()
try:
    asyncio.run(process.start())
except KeyboardInterrupt:
    print("Server is stopped")
