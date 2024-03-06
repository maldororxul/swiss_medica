""" Управление чатами Tawk, интеграция с Amo

Форматы данных, приходящих от Tawk:
{
    'chatId': 'aaf4ff90-3a7d-11ee-86b6-71ef2c3aef2f',
    'visitor': {'name': 'Test Name', 'city': 'batumi', 'country': 'GE'},
    'message': {'sender': {'type': 'visitor'}, 'text': 'Name : Test Name\r\nPhone : 79216564906', 'type': 'msg'},
    'time': '2023-08-14T08:37:11.874Z',
    'event': 'chat:start',
    'property': {'id': '64d0945994cf5d49dc68dd99', 'name': 'CDV'} <-- это название чата, с ним будем мапать
}
{
    'chatId': '61880e20-4d46-11ee-871d-09e91a719de2',
    'visitor': {'name': 'ChatEnds','city': 'batumi', 'country': 'GE'},
    'time': '2023-09-07T06:20:09.450Z',
    'event': 'chat:end',
    'property': {'id': '64d0945994cf5d49dc68dd99', 'name': 'cdv_main'}
}
{
    "referer": ...,
   "questions":[
      {
         "label":"Submitted From",
         "answer":"https://swiss-medica-2e0e7bc937df.herokuapp.com/?utm_source=test_campaign&utm_medium=test_medium&utm_campaign=test_medium&utm_id=test_campaighn&utm_term=test_term&utm_content=test_content"
      },
      {
         "label":"Name",
         "answer":"TestOfflineForm"
      },
      {
         "label":"Email",
         "answer":"TestOfflineForm@gmail.com"
      },
      {
         "label":"Phone",
         "answer":"+99595959595"
      },
      {
         "label":"Question",
         "answer":"TestOfflineForm"
      }
   ],
   "name":"TestOfflineForm",
   "email":"TestOfflineForm@gmail.com",
   "phone":"+99595959595"
}
"""
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs
from flask import Response, Request

from app.amo.api.client import SwissmedicaAPIClient, DrvorobjevAPIClient
from app.models.chat import SMChat, CDVChat
from app.tawk.api import TawkRestClient
from config import Config
from modules.utils.utils.functions import clear_phone


API_CLIENT = {
    'SM': SwissmedicaAPIClient,
    'CDV': DrvorobjevAPIClient,
    'sm': SwissmedicaAPIClient,
    'cdv': DrvorobjevAPIClient,
    'swissmedica': SwissmedicaAPIClient,
    'drvorobjev': DrvorobjevAPIClient,
}

TAWK_CHAT_MODEL = {
    'SM': SMChat,
    'CDV': CDVChat,
    'sm': SMChat,
    'cdv': CDVChat,
    'swissmedica': SMChat,
    'drvorobjev': CDVChat,
}


class TawkController:
    """ Класс для управления чатами Tawk, интеграции с Amo """

    def handle(self, request: Request):
        """ Прилетают примерно такие данные
        {
            'questions': [
                {'label': 'Name', 'answer': '...'},
                {'label': 'Email', 'answer': '...'},
                {'label': 'Phone', 'answer': '...'},
                {'label': 'Your question', 'answer': '...'}
            ],
            'name': '...',
            'email': '...',
            'phone': '...',
            'submittedFrom': 'https://...',
            'referrer': ''
        }
        """
        data = request.json or {}
        # print('DATA FROM TAWK', data)
        lead_data = None
        # Кейс 1. Данные из оффлайн-формы, филиал и настройки будем определять по адресу сайта
        site = self.__get_offline_form_site(data=data)
        if site:
            lead_data = self.__handle_offline_form_event(site=site, data=data)
        # Кейс 2. Перед нами сообщение с заполненной контактной формой (pre-chat)
        prop = data.get('property') or {}
        chat_name = prop.get('name')
        if chat_name:
            lead_data = self.__handle_chat_end_event(
                chat_name=chat_name,
                channel_id=prop.get('id'),
                chat_id=data['chatId']
            )
        if not lead_data:
            return Response(status=204)
        self.__add_or_update_lead(data=lead_data)
        return Response(status=200)

    @staticmethod
    def __get_offline_form_site(data: Dict) -> Optional[str]:
        for question in data.get('questions') or []:
            if question.get('label') != "Submitted From":
                continue
            url = question.get('answer')
            return url
        return data.get('submittedFrom')

    @staticmethod
    def __get_customer_data(person_dict: Dict) -> [Tuple[str, str, str, str]]:
        # имя и номер пациента
        name_data = person_dict.get('name')
        name = f"{name_data.get('first') or ''} {name_data.get('last') or ''}".strip()
        phones_data = person_dict.get('phones') or []
        if not phones_data:
            return None
        emails_data = person_dict.get('emails') or []
        if not emails_data:
            return None
        phone = clear_phone(phones_data[0])
        email = emails_data[0]
        referer = (person_dict.get('customAttributes') or {}).get('ref')
        return name, phone, email, referer

    @staticmethod
    def __get_config_by_site(site: str) -> Tuple:
        parsed_url = urlparse(site)
        site = f"{parsed_url.scheme}://{parsed_url.netloc}".lower()
        for key, value in Config().tawk.items():
            for _site in value.get('sites') or []:
                if _site.lower() == site:
                    return key, value
        return None, None

    def __handle_offline_form_event(self, site: str, data: Dict) -> Optional[Dict]:
        """ Прилетают примерно такие данные
        {
            'questions': [
                {'label': 'Name', 'answer': '...'},
                {'label': 'Email', 'answer': '...'},
                {'label': 'Phone', 'answer': '...'},
                {'label': 'Your question', 'answer': '...'}
            ],
            'name': '...',
            'email': '...',
            'phone': '...',
            'submittedFrom': 'https://...',
            'referrer': ''
        }
        """
        # зная сайт, попытаемся вытащить из общего конфига TAWK конфиг конкретного канала
        chat_name, config = self.__get_config_by_site(site=site)
        if not config:
            return None
        utm_dict = self.__get_utm_dict_from_url(url=site)
        msg = None
        for question in data.get('questions') or []:
            if 'question' in question['label'].lower():
                msg = question['answer']
                break
        return {
            'chat_name': chat_name,
            'name': data.get('name'),
            'phone': data.get('phone'),
            'email': data.get('email'),
            # referer - это кастомный атрибут, передаваемый при загрузке виджета чата, прокидывается вручную
            'referer': data.get('referer'),
            'utm_dict': utm_dict,
            'responsible_user_id': 0,
            'tawk_data': {},
            'msg': msg
        }

    def __handle_chat_end_event(self, chat_name: str, channel_id: str, chat_id: str) -> Optional[Dict]:
        # по имени чата определяем филиал
        config = Config().tawk.get(chat_name) or {}
        branch = config.get('branch')
        if not branch:
            return None
        tawk_data = self.__get_tawk_data(channel_id=channel_id, chat_id=chat_id, branch=branch)
        if not tawk_data:
            return None
        name, phone, email, referer = self.__get_customer_data(person_dict=tawk_data.get('person') or {})
        if not phone or not email:
            return None
        # разбираем utm-метки из source
        utm_dict = self.__get_utm_dict_from_url(url=tawk_data.get('source'))
        # определяем идентификатор ответственного пользователя
        responsible_user_id = self.__get_responsible_user_id(
            manager_id=tawk_data.get('manager').get('id'),
            branch=branch
        )
        return {
            'chat_name': chat_name,
            'name': name,
            'phone': phone,
            'email': email,
            'referer': referer,
            'utm_dict': utm_dict,
            'responsible_user_id': responsible_user_id,
            'tawk_data': tawk_data,
        }

    @staticmethod
    def __add_or_update_lead(data: Dict):
        """ Создает, либо обновляет сделку с чатом Jivo

        Args:
            data: данные в формате {
                'chat_name': ...,
                'name': ...,
                'phone': ...,
                'email': ...,
                'referer': ...,
                'utm_dict': {},
                'responsible_user_id': 0,
                'tawk_data': {},
                'msg': ... (optional)
            }
        """
        chat_name = data.get('chat_name')
        config = Config().tawk.get(chat_name) or {}
        tawk_data = data.get('tawk_data') or {}
        utm_dict = data.get('utm_dict')
        amo_client = API_CLIENT.get(config.get('branch'))()
        existing_leads = list(amo_client.find_leads(query=data.get('phone'), limit=1))
        lead_id = None
        if existing_leads:
            # лид найден - дописываем чат в ленту событий / примечаний
            lead_id = int(existing_leads[0]['id'])
        else:
            # лид не найден - создаем
            lead_added = amo_client.add_lead_simple(
                title=f'TEST! Lead from Tawk: {data.get("name")}',
                name=data.get("name"),
                tags=['Tawk', chat_name],
                referer=data.get('referer'),
                utm=utm_dict,
                pipeline_id=int(config.get('pipeline_id')),
                status_id=int(config.get('status_id')),
                contacts=[
                    {'value': data.get('phone'), 'field_id': int(config.get('phone_field_id')), 'enum_code': 'WORK'},
                    {'value': data.get('email'), 'field_id': int(config.get('email_field_id')), 'enum_code': 'WORK'},
                ],
                responsible_user_id=data.get('responsible_user_id')
            )
            # response from Amo
            #   [{"id":24050975,"contact_id":28661273,"company_id":null,"request_id":["0"],"merged":false}]
            added_lead_data = lead_added.json()
            try:
                lead_id = int(added_lead_data[0]['id'])
            except:
                pass
        messages = tawk_data.get('messages') or data.get('msg')
        if lead_id and messages:
            amo_client.add_note_simple(entity_id=lead_id, text=messages)

    @staticmethod
    def __get_responsible_user_id(manager_id: str, branch: str) -> int:
        managers = Config().managers.get(branch) or {}
        tawk_amo_dict = {
            value['tawk_id']: value['amo_id']
            for value in managers.values()
            if value['tawk_id'] and value['amo_id']
        }
        return tawk_amo_dict.get(manager_id) or 0

    @staticmethod
    def __get_tawk_data(channel_id: str, chat_id: str, branch: str) -> Optional[Dict]:
        # данные нового чата могли не успеть записаться в базу Tawk, поэтому циклим
        tawk_data = None
        counter = 0
        max_counter = 24
        while not tawk_data:
            counter += 1
            if counter > max_counter:
                break
            tawk_data = TawkRestClient(
                branch=branch
            ).get_messages_text_and_person(channel_id=channel_id, chat_id=chat_id)
            time.sleep(5)
        return tawk_data

    @staticmethod
    def __get_utm_dict_from_url(url: Optional[str]) -> Dict:
        if url:
            parsed_url = urlparse(url)
            return parse_qs(parsed_url.query)
        return {}
