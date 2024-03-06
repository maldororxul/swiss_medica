""" Управление подстраховкой проброса лидов в Amo с сайтов на Tilda, startstemcells и проч. """
__author__ = 'ke.mizonov'
import gc
import time
from datetime import datetime
from typing import Dict, Optional, List
import telebot
from flask import Flask
from app.google_api.client import GoogleAPIClient
from config import Config
from modules.utils.utils.functions import clear_phone


def start_leads_insurance_iteration(app: Flask, branch: str):
    """ Перезапускает все проверки лидов """
    leads_controller = LeadsInsurance(branch=branch)
    leads_controller.start(app=app)
    del leads_controller
    gc.collect()


class LeadsInsurance:
    """ Класс, управляющий проверкой лидов """
    leads_storage_limit = 1000

    def __init__(self, branch: Optional[str] = None):
        self.__branch = branch

    @property
    def __book_id(self) -> str:
        return Config().leads_insurance.get(self.__branch)

    @property
    def __channel_id(self) -> str:
        return Config().sm_leads_insurance_channel

    def start(self, app: Flask):
        """ Перезапускает все проверки лидов """
        from app.main.leads_insurance.constants import API_CLIENT
        with app.app_context():
            amo_client = API_CLIENT.get(self.__branch)()
            self.__start(amo_client=amo_client)

    def is_spam(self, line):
        """ Из лида делаем line: {'phone': ..., 'email': ..., 'msg': ...} """
        spam_rules = self.__build_spam_rules()
        return self.__is_spam(rules=spam_rules, line=line)

    def __start(self, amo_client):
        leads_google_client = GoogleAPIClient(book_id=self.__book_id, sheet_title='Leads')
        collection = leads_google_client.get_sheet()
        spam_rules = self.__build_spam_rules()
        saved_leads = []
        for row, line in enumerate(collection, 1):
            if line.get('status'):
                continue
            phone, email = clear_phone(line.get('phone') or ''), line.get('email')
            contact = None
            if phone and len(phone) >= 9:
                contacts = amo_client.find_contacts(query=phone[-8:], field_code='PHONE', limit=1) or [{}]
                contact = contacts[0]
            if not contact and email and '@' in email and len(email) > 4:
                contacts = amo_client.find_contacts(query=email, field_code='EMAIL', limit=1) or [{}]
                contact = contacts[0]
            if not contact:
                status = 'contact not found'
                is_spam = self.__is_spam(rules=spam_rules, line=line)
                # делаем пометку о спаме в таблице
                leads_google_client.write_value_to_cell(row=row, col=7, value='1' if is_spam else '0')
                if not is_spam:
                    # отправляем оповещение в Telegram
                    saved_leads.append(line)
            else:
                # поскольку у нас наверняка есть дубли в Amo, дополнительно сверимся по дате создания контакта
                contact_date = datetime.fromtimestamp(int(contact.get('created_at'))).date()
                line_date = datetime.strptime(line.get('date'), "%Y-%m-%d %H:%M:%S").date()
                status = 'new contact found' if contact_date == line_date else 'old contact found'
            leads_google_client.write_value_to_cell(row=row, col=6, value=status)
            time.sleep(0.3)
        # отправляем оповещение в Telegram
        self.__send_telegram_notification(saved_leads=saved_leads)
        # удаляем старые записи о лидах
        if len(collection) > self.leads_storage_limit:
            rows_number = len(collection) - self.leads_storage_limit
            leads_google_client.delete_row(row=2, rows_number=rows_number+1)

    def __build_spam_rules(self) -> Dict:
        """ Строит словарь с правилами спама

        Returns:
            Списки спамовых телефонов, адресов почты и фрагментов сообщений {'phone': [], 'email': [], 'msg': []}
        """
        spam_google_client = GoogleAPIClient(book_id=self.__book_id, sheet_title='_spam_filter')
        spam_rules = {'phone': [], 'email': [], 'msg': []}
        for line in spam_google_client.get_sheet() or []:
            if line.get('dont_use') and line.get('dont_use') == 1:
                continue
            if line.get('phone'):
                spam_rules['phone'].append(clear_phone(line['phone']))
            if line.get('email'):
                spam_rules['email'].append(line['email'].lower().strip())
            if line.get('msg'):
                spam_rules['msg'].append(line['msg'].lower().strip())
        return spam_rules

    def __send_telegram_notification(self, saved_leads: List[Dict]):
        """ Отправляет оповещение в телеграм

        Args:
            saved_leads: список лидов, не попавших в Amo и прошедших спам-фильтр
        """
        if not saved_leads:
            return
        step = 1
        total = int(len(saved_leads) / step) or 1
        for i in range(0, total+1):
            message = ''
            for lead in saved_leads[i*step:i*step+step]:
                text = lead.get('msg') or ''
                if not lead.get('source'):
                    continue
                if not lead.get('phone') and lead.get('email'):
                    continue
                if len(text) > 3500:
                    text = f"{text[:3000]} <...>"
                item = f"Source: {lead.get('source')}\n" \
                       f"Name: {lead.get('name')}\n" \
                       f"Phone: {lead.get('phone')}\n" \
                       f"Email: {lead.get('email')}\n" \
                       f"Msg: {text}".strip()
                message = f'Restored lead\n{item}' if not message else f'{message}\n{item}'
            if not message:
                continue
            telegram_bot_token = Config().sm_telegram_bot_token
            telebot.TeleBot(telegram_bot_token).send_message(self.__channel_id, message)
            time.sleep(2)

    @staticmethod
    def __is_spam(rules: Dict, line: Dict) -> bool:
        """ Проверяет, является ли заявка спамом

        Args:
            rules: списки спамовых номеров, адресов и фрагментов сообщений
            line: строка данных, подлежащая проверке на спам

        Returns:
            True - заявка является спамом, иначе Flase
        """
        is_spam = False
        if line.get('phone'):
            phone = clear_phone(line['phone'])
            is_spam = phone in rules['phone']
        if not is_spam and line.get('email'):
            is_spam = line['email'].lower().strip() in rules['email']
        if not is_spam:
            msg = line.get('msg')
            if not msg:
                return False
            msg = msg.lower()
            for _spam_msg in rules['msg']:
                if _spam_msg in msg:
                    return True
        return is_spam
