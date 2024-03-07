""" API-клиент для работы с сервисами Google (в частности: с Google Sheets)

Notes:
    Авторизация осуществляется через сервисный аккаунт:
        python-analytics-client@swiss-medica-359005.iam.gserviceaccount.com

    Этот аккаунт имеет доступ к API, и ему нужно вручную открывать доступ к тем Google Sheets,
    с которыми он должен работать

References:
    https://habr.com/ru/post/488756/
"""
__author__ = 'ke.mizonov'
import decimal
from datetime import datetime, timedelta
from time import sleep
from typing import Dict, List, Optional, Union
from googleapiclient.discovery import build, Resource
from google.oauth2 import service_account
from googleapiclient.errors import HttpError

from config import Config
from app.google_api.constants import SCOPES
from app.google_api.errors import SpreadSheetNotFoundError

DATE_FORMAT = '%d.%m.%Y'
WEEKDAYS = {
    0: 'пн',
    1: 'вт',
    2: 'ср',
    3: 'чт',
    4: 'пт',
    5: 'сб',
    6: 'вс',
}


class GoogleAPIClient:
    """ API-клиент для работы с сервисами Google (в частности: с Google Sheets) """

    def __init__(
        self,
        book_id: Optional[str] = None,
        sheet_title: Optional[str] = None,
        start_col: str = 'A',
        last_col='AY'
    ):
        """
        Args:
            book_id: текстовый идентификатор книги
            sheet_title: название листа
            start_col: колонка, с которой начинаются данные
            last_col: колонка, на которой заканчиваются данные
        """
        # авторизация
        self.sheets_service: Resource = self.__auth()
        self.__book_id = book_id
        self.__sheet_title = sheet_title
        self.__start_col = start_col
        self.__last_col = last_col

    @property
    def sheet_id(self) -> str:
        """ Идентификатор листа """
        return self.__get_sheet_id(sheet_title=self.__sheet_title)

    @property
    def sheets(self) -> Dict:
        """
        Returns:
            Словарь идентификаторов и имен всех листов книги
        """
        collection = {}
        for sheet in self.sheets_service.spreadsheets().get(spreadsheetId=self.__book_id).execute().get('sheets'):
            props = sheet['properties']
            collection[props['sheetId']] = props['title']
        return collection

    def clear_all_except_title(self):
        """ Очищает лист, оставляя только заголовки """
        data_list = []
        # находим следующий (свободный) за последним заполненным ряд
        rows = self.get_sheet()
        for i in range(len(rows)):
            line = ['' for x in range(len(rows[0]))]
            data_list.append(line)
        # сначала заполнять ряды, затем столбцы (т.е. самые внутренние списки в values - это ряды)
        body = {
            "valueInputOption": "USER_ENTERED",
            "data": [{
                "range": f"{self.__sheet_title}!{self.__start_col}{2}",
                "majorDimension": "ROWS",
                "values": data_list
            }]
        }
        self.sheets_service.spreadsheets().values().batchUpdate(spreadsheetId=self.__book_id, body=body).execute()

    def delete_row(self, row: int, rows_number: int = 1, sheet_id: Optional[str] = None):
        """ Удаляет строку на указанном листе

        Args:
            sheet_id: идентификатор листа
            row: номер удаляемой строки
            rows_number: количество удаляемых строк
        """
        sheet_id = sheet_id or self.sheet_id
        request = {
            "requests": [{
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row - 1,  # 0-indexed
                        "endIndex": row + rows_number - 1
                    }
                }
            }]
        }
        self.sheets_service.spreadsheets().batchUpdate(spreadsheetId=self.__book_id, body=request).execute()

    def get_sheet(self, dictionary: bool = True) -> Union[List[Dict], List[List]]:
        """ Получить данные с листа

        Args:
            dictionary: True - в виде списка словарей

        Returns:
            список словарей или список списков с данными с листа
        """
        res = []
        # Call the Sheets API
        try:
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.__book_id,
                range=f'{self.__sheet_title}!A1:{self.__last_col}').execute()
            values = result.get('values', [])
        except Exception as e:
            print(e)
            return res

        if not values:
            return res
        else:
            for row in values:
                res.append(row)
            if dictionary and len(res) > 0:
                d_res = list()
                for r in range(1, len(res)):
                    line = dict()
                    for n, k in enumerate(res[0]):
                        try:
                            line[k] = res[r][n]
                        except:
                            pass
                    d_res.append(line)
                return d_res
        return res

    def paint_cells(self, sheet_id: str, red: float = 0, green: float = 0, blue: float = 0):
        """ Закрашивает A1:A3 на указанном листе в заданный цвет

        Args:
            sheet_id: идентификатор листа
            red: доля красного
            green: доля зеленого
            blue: доля синего

        Returns:

        """
        request = {
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 3
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {
                                    "red": red,
                                    "green": green,
                                    "blue": blue
                                }
                            }
                        },
                        "fields": "userEnteredFormat.backgroundColor"
                    }
                }
            ]
        }
        self.sheets_service.spreadsheets().batchUpdate(spreadsheetId=self.__book_id, body=request).execute()

    def sort(self, sheet_id: Optional[str] = None, column: int = 0):
        sheet_id = sheet_id or self.__get_sheet_id(sheet_title=self.__sheet_title)
        sort_request = {
            "requests": [
                {
                    "sortRange": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,  # с начала листа
                        },
                        "sortSpecs": [
                            {
                                "dimensionIndex": column,
                                "sortOrder": "ASCENDING"
                            }
                        ]
                    }
                }
            ]
        }
        self.sheets_service.spreadsheets().batchUpdate(spreadsheetId=self.__book_id, body=sort_request).execute()

    def write_value_to_cell(self, row: int, col: int, value: str):
        """ Записать значение в ячейку таблицы

        Args:
            row: Номер строки
            col: Номер колонки
            value: Значение для записи
        """
        sheet_range = f"{self.__sheet_title}!{chr(ord('A') + col)}{row + 1}"  # Пример формирования диапазона
        values = [[value]]  # Значение для записи (в виде двумерного списка)

        body = {
            "values": values
        }

        try:
            self.sheets_service.spreadsheets().values().update(
                spreadsheetId=self.__book_id,
                range=sheet_range,
                valueInputOption="RAW",  # Если значение не должно интерпретироваться как формула
                body=body
            ).execute()
        except HttpError as e:
            print(f"An error occurred: {e}")

    def update_arrival_schedule(self, source_sheet_title: str):
        """ Обновление расписания клиник

        Args:
            source_sheet_title: название листа, с которого читаются исходные данные
        """
        # считываем данные таблицы Arrival и строим на их основе расписание
        rows = GoogleAPIClient(book_id=self.__book_id, sheet_title=source_sheet_title).get_sheet()
        # уникальные клиники берем с листа расписания
        result = self.sheets_service.spreadsheets().values().get(
            spreadsheetId=self.__book_id,
            range=f'{self.__sheet_title}!A1:1').execute()
        values = result.get('values', [])
        if not values:
            return []
        unique_clinics = values[0][3:]
        # границы по датам
        from_dt, to_dt = None, None
        for row in rows:
            if not row.get('Hotel name'):
                continue
            arrival_str, departure_str = row.get('Arrival Date'), row.get('Departure Date')
            if not arrival_str or not departure_str:
                continue
            arrival_dt = datetime.strptime(arrival_str, '%Y-%m-%d').date()
            departure_dt = datetime.strptime(departure_str, '%Y-%m-%d').date()
            if not from_dt or arrival_dt < from_dt:
                from_dt = arrival_dt
            if not to_dt or departure_dt > to_dt:
                to_dt = departure_dt
        if not from_dt or not to_dt:
            return []
        # готовим "рыбу" данных в рамках границ дат
        schedule_dict = {}
        curr_dt = from_dt
        while curr_dt <= to_dt:
            if curr_dt not in schedule_dict:
                schedule_dict[curr_dt] = {}
            for clinic in unique_clinics:
                if clinic not in schedule_dict[curr_dt]:
                    schedule_dict[curr_dt][clinic] = 0
            curr_dt = curr_dt + timedelta(1)
        # заполняем данные
        for row in rows:
            arrival_str, departure_str = row.get('Arrival Date'), row.get('Departure Date')
            if not arrival_str or not departure_str:
                continue
            arrival_dt = datetime.strptime(arrival_str, '%Y-%m-%d').date()
            departure_dt = datetime.strptime(departure_str, '%Y-%m-%d').date()
            clinic = row.get('Hotel name')
            curr_dt = arrival_dt
            while curr_dt <= departure_dt:
                schedule_dict[curr_dt][clinic] += 1
                curr_dt = curr_dt + timedelta(1)
        schedule = []
        for date_key, clinics_data in schedule_dict.items():
            total = sum([clinics_data.get(clinic) for clinic in unique_clinics if clinics_data.get(clinic)])
            line = {
                'Date': date_key.strftime(DATE_FORMAT),
                'WD': WEEKDAYS.get(date_key.weekday()),
                'Total': total if total > 0 else '',
            }
            line.update({clinic: clinics_data.get(clinic) or '' for clinic in unique_clinics})
            schedule.append(line)
        return schedule

    def update_collection(
        self,
        collection: List[Dict],
        unique_key: Optional[str] = None,
        has_dates: bool = False,
        archive_sheet: Optional[str] = None
    ):
        """ Синхронизация данных на листе

        Args:
            collection: данные в виде списка словарей
            unique_key: поле, значение которого считается уникальным (для перезаписи)
            has_dates: на листе в первой колонке created_at, во второй колонке updated_at
            archive_sheet: имя архивного листа, на который перемещаются удаляемые данные
        """
        if not collection:
            return
        # находим id листа
        sheet_id = self.sheet_id
        # красим A1 в красный в знак того, что запущено обновление
        self.paint_cells(sheet_id=sheet_id, red=0.8)
        # уже имеющиеся на листе данные
        rows = self.get_sheet()
        # готовим словари обновляемых / существующих данных {unique_value: collection_item}
        collection_dict = {str(item.get(unique_key)): item for item in collection if item.get(unique_key)}
        rows_dict = {str(item.get(unique_key)): item for item in rows if item.get(unique_key)}
        # обновляемые записи, а также удаляемые записи (будут перемещены в архив)
        updating = []
        removing = []
        exclude_keys = [unique_key]
        if has_dates:
            exclude_keys.extend(['created_at', 'updated_at'])
        for row_item in rows:
            unique_value = row_item.get(unique_key)
            if not unique_value:
                continue
            collection_item = collection_dict.get(str(unique_value))
            if collection_item:
                # действительно ли запись нуждается в обновлении?
                #   будут сравниваться все ключи коллекции, поэтому подразумевается, что
                #   created_at, updated_at и сторонних полей в коллекции нет
                need_update = False
                for key, new_value in collection_item.items():
                    if key in exclude_keys:
                        continue
                    if str(new_value) != str(row_item.get(key) or ''):
                        need_update = True
                        break
                if need_update:
                    if has_dates:
                        with_dates = {
                            'created_at': row_item.get('created_at'),
                            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        with_dates.update(collection_item)
                    else:
                        with_dates = collection_item
                    updating.append(with_dates)
            else:
                removing.append(row_item)
        # добавляемые записи
        adding = []
        for collection_item in collection:
            unique_value = collection_item.get(unique_key)
            if not unique_value:
                continue
            row_item = rows_dict.get(str(unique_value))
            if row_item:
                continue
            if has_dates:
                with_dates = {
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'updated_at': ''
                }
                with_dates.update(collection_item)
            else:
                with_dates = collection_item
            adding.append(with_dates)

        # записываем обновляемые данные
        for item in updating:
            unique_value = str(item.get(unique_key))
            start_row = None
            for num, row in enumerate(rows, 1):
                if str(row.get(unique_key)) == unique_value:
                    start_row = num
                    break
            if not start_row:
                continue
            self.__write(collection=[item], start_row=start_row, pause=.5)
        # записываем добавляемые данные
        next_row = len(rows) + 1
        # добавляем строки (условие - должна существовать пустая последняя строка!)
        self.__add_rows(sheet_id=sheet_id, next_row=next_row, length=len(adding))
        self.__write(collection=adding, start_row=next_row)
        # перемещаем удаляемые строки в архив
        if archive_sheet:
            GoogleAPIClient(
                book_id=self.__book_id,
                sheet_title=archive_sheet
            ).write_data_to_sheet(data=removing)
        # удаляем удаляемые строки
        for item in removing:
            unique_value = str(item.get(unique_key))
            for row_num, row in enumerate(rows, 2):
                if unique_value != str(row.get(unique_key)):
                    continue
                self.delete_row(sheet_id=sheet_id, row=row_num)
                rows.remove(row)
                break
        # красим A1 в белый в знак того, что обновление завершено
        self.paint_cells(sheet_id=sheet_id, red=1, green=1, blue=1)

    def add_row(self, row_data_dict: Dict):
        rows = self.get_sheet() or []
        next_row = len(rows) + 1
        self.__add_rows(sheet_id=self.sheet_id, next_row=next_row, length=1)
        self.__write(collection=[row_data_dict], start_row=next_row)

    def update_leads_quantity(self, users: Dict):
        """ Обновляет количество лидов по менеджерам

        Args:
            users: словарь менеджеров / количества лидов
        """
        # Read the names from the first row
        names_range = f"{self.__sheet_title}!1:1"
        names_response = self.sheets_service.spreadsheets().values().get(
            spreadsheetId=self.__book_id,
            range=names_range
        ).execute()
        names = names_response.get('values', [])[0]
        # Prepare the values for the second row
        values = [users.get(name, '') for name in names]
        # Write the values to the second row
        self.sheets_service.spreadsheets().values().update(
            spreadsheetId=self.__book_id,
            range=f"{self.__sheet_title}!2:2",
            valueInputOption='RAW',
            body={'values': [values]}
        ).execute()

    def write_titles(self, titles: List[str]):
        """ Заполняет заголовки листа

        Args:
            titles: список заголовком
        """
        body = {
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": f"{self.__sheet_title}!{self.__start_col}{1}",
                 "majorDimension": "ROWS",
                 # сначала заполнять ряды, затем столбцы (т.е. самые внутренние списки в values - это ряды)
                 "values": [titles]},
            ]
        }
        self.sheets_service.spreadsheets().values().batchUpdate(spreadsheetId=self.__book_id, body=body).execute()

    def write_data_to_sheet(
        self,
        data: List[Dict],
        start_row: Optional[int] = None,
        rewrite: bool = False,
        shift: bool = True
    ):
        """ Запись данных на лист онлайн-таблицы

        Args:
            data: данные
            start_row: с какой строки начинать запись
            rewrite: True - удалить старые данные (кроме заголовков)
            shift: True - смещение строк, False - без смещения
        """
        # находим id листа
        sheet_id = self.sheet_id
        # удаляем старые данные, если требуется перезапись
        if rewrite:
            self.clear_all_except_title()
        # находим следующий (свободный) за последним заполненным ряд
        if start_row is None:
            rows = self.get_sheet()
            start_row = len(rows) + 1
        # добавляем строки (условие - должна существовать пустая последняя строка!)
        if not rewrite:
            self.__add_rows(sheet_id=sheet_id, next_row=start_row, length=len(data), shift=shift)
        self.__write(collection=data, start_row=start_row)

    def __add_rows(self, sheet_id: str, next_row: int, length: int, shift: bool = True):
        """ Добавляет строки

        Args:
            sheet_id: идентификатор листа
            next_row: номер строки
            length: количество вставляемых строк
            shift: требуется ли смещение
        """
        body = {
            "requests": [
                {
                    "insertRange": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": next_row,
                            "endRowIndex": next_row + length
                        },
                        "shiftDimension": 'ROWS' if shift else None
                    }
                }
            ]
        }
        self.sheets_service.spreadsheets().batchUpdate(spreadsheetId=self.__book_id, body=body).execute()

    def __get_sheet_id(self, sheet_title):
        """ Идентификатор листа

        Returns:
            Находит идентификатор листа по названию

        Raises:
            SpreadSheetNotFoundError: Лист онлайн-таблицы не найден
        """
        for sheet in self.sheets_service.spreadsheets().get(spreadsheetId=self.__book_id).execute().get('sheets'):
            if sheet['properties']['title'] == sheet_title:
                return sheet['properties']['sheetId']
        raise SpreadSheetNotFoundError(f'Лист "{sheet_title}" не найден в онлайн-таблице')

    def __write(self, collection: List[Dict], start_row: int, pause: float = .0):
        """ Запись данных на лист

        Args:
            collection: данные в виде списка словарей
            start_row: с какой строки начинать запись
        """
        data_list = self.__listdict_to_listlist(collection=collection)
        body = {
            "valueInputOption": "USER_ENTERED",
            "data": [
                {
                    "range": f"{self.__sheet_title}!{self.__start_col}{start_row + 1}",
                    "majorDimension": "ROWS",
                    # сначала заполнять ряды, затем столбцы (т.е. самые внутренние списки в values - это ряды)
                    "values": data_list
                },
            ]
        }
        self.sheets_service.spreadsheets().values().batchUpdate(spreadsheetId=self.__book_id, body=body).execute()
        sleep(pause)

    @staticmethod
    def __auth() -> Resource:
        """ Авторизация (через сервисный аккаунт)

        Returns:
            объект для обращения к гуглу по API
        """
        creds = service_account.Credentials.from_service_account_info(
            Config().google_credentials,
            scopes=SCOPES
        )
        return build('sheets', 'v4', credentials=creds)

    @staticmethod
    def __listdict_to_listlist(collection: List[Dict]) -> List[List]:
        """ Приводит список словарей к списку списков

        Args:
            collection: данные листа в виде списка словарей

        Returns:
            данные листа в виде списка списков
        """
        data_list = []
        for i in collection:
            line = list()
            for ii in i.values():
                if type(ii) is decimal.Decimal:
                    line.append(float(ii))
                else:
                    line.append(ii)
            data_list.append(line)
        return data_list
