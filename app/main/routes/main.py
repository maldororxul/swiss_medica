""" Общие маршруты """
__author__ = 'ke.mizonov'
from datetime import datetime
from typing import Union, Type, Dict, Optional
from apscheduler.jobstores.base import JobLookupError
from flask import render_template, current_app, redirect, url_for, request, Response
from app import db, socketio
from app.amo.api.client import SwissmedicaAPIClient, DrvorobjevAPIClient
from app.amo.processor.processor import GoogleSheets
from app.google_api.client import GoogleAPIClient
from app.main import bp
from app.main.arrival.handler import waiting_for_arrival
from app.main.leads_insurance.handler import LeadsInsurance
from app.main.processors import DATA_PROCESSOR
from app.main.routes.utils import get_data_from_post_request, get_args_from_url
from app.main.tasks import SchedulerTask
from app.main.utils import DateTimeEncoder
from app.models.chat import SMChat, CDVChat
from app.models.data import SMData, CDVData
from app.models.raw_lead_data import SMRawLeadData, CDVRawLeadData
from app.tawk.controller import TawkController
from app.utils.country_by_ip import get_country_by_ip
from app.whatsapp.controller import WhatsAppController
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

RAW_LEAD = {
    'SM': SMRawLeadData,
    'CDV': CDVRawLeadData,
    'sm': SMRawLeadData,
    'cdv': CDVRawLeadData,
    'swissmedica': SMRawLeadData,
    'drvorobjev': CDVRawLeadData,
}

TAWK_CHAT_MODEL = {
    'SM': SMChat,
    'CDV': CDVChat,
    'sm': SMChat,
    'cdv': CDVChat,
    'swissmedica': SMChat,
    'drvorobjev': CDVChat,
}

DATA_MODEL = {
    'sm': SMData,
    'cdv': CDVData
}


def start_get_data_from_amo_scheduler(branch: str):

    scheduler_id = f'get_data_from_amo_{branch}'
    lowest_dt = datetime.strptime(request.args.get('time', default=None, type=str), "%Y-%m-%dT%H:%M")
    # current_app - это проксированный экземпляр приложения,
    # _get_current_object - доступ к объекту приложения напрямую
    # с проксированным объектом получается некорректный контекст => костыляем
    app = current_app._get_current_object()
    # загрузка данных из Amo CDV
    try:
        app.scheduler.remove_job(scheduler_id)
    except JobLookupError:
        pass
    processor = DATA_PROCESSOR.get(branch)()
    if not app.scheduler.get_job(scheduler_id):
        app.scheduler.add_job(
            id=scheduler_id,
            func=socketio.start_background_task,
            args=[SchedulerTask().get_data_from_amo, app, branch, lowest_dt],
            trigger='interval',
            seconds=60,
            max_instances=1
        )
        if not app.scheduler.running:
            app.scheduler.start()
        with app.app_context():
            processor.log.add(text=f'Amo data loader has started', log_type=1)
            return Response(status=204)
    with app.app_context():
        processor.log.add(text=f'Amo data loader is already running', log_type=1)
    return Response(status=204)
    # return render_template('index.html')


def stop_get_data_from_amo_scheduler(branch: str):
    scheduler_id = f'get_data_from_amo_{branch}'
    # current_app - это проксированный экземпляр приложения,
    # _get_current_object - доступ к объекту приложения напрямую
    # с проксированным объектом получается некорректный контекст => костыляем
    app = current_app._get_current_object()
    # загрузка данных из Amo CDV
    try:
        app.scheduler.remove_job(scheduler_id)
    except JobLookupError:
        pass
    processor = DATA_PROCESSOR.get(branch)()
    # if not app.scheduler.running:
    #     app.scheduler.start()
    with app.app_context():
        processor.log.add(text=f'Amo data loader has stopped', log_type=1)
    return Response(status=204)


def start_update_pivot_data(branch: str):
    scheduler_id = f'update_pivot_data_{branch}'
    # current_app - это проксированный экземпляр приложения,
    # _get_current_object - доступ к объекту приложения напрямую
    # с проксированным объектом получается некорректный контекст => костыляем
    app = current_app._get_current_object()
    # загрузка данных из Amo CDV
    try:
        app.scheduler.remove_job(scheduler_id)
    except JobLookupError:
        pass
    processor = DATA_PROCESSOR.get(branch)()
    if not app.scheduler.get_job(scheduler_id):
        app.scheduler.add_job(
            id=scheduler_id,
            func=socketio.start_background_task,
            args=[SchedulerTask().update_pivot_data, app, branch],
            trigger='interval',
            seconds=60,
            max_instances=1
        )
        if not app.scheduler.running:
            app.scheduler.start()
        with app.app_context():
            processor.log.add(text=f'Amo data builder has started', log_type=1)
            return Response(status=204)
    with app.app_context():
        processor.log.add(text=f'Amo data builder is already running', log_type=1)
    return Response(status=204)


def stop_update_pivot_data(branch: str):
    scheduler_id = f'update_pivot_data_{branch}'
    # current_app - это проксированный экземпляр приложения,
    # _get_current_object - доступ к объекту приложения напрямую
    # с проксированным объектом получается некорректный контекст => костыляем
    app = current_app._get_current_object()
    # загрузка данных из Amo CDV
    try:
        app.scheduler.remove_job(scheduler_id)
    except JobLookupError:
        pass
    processor = DATA_PROCESSOR.get(branch)()
    # if not app.scheduler.running:
    #     app.scheduler.start()
    with app.app_context():
        processor.log.add(text=f'Amo data builder has stopped', log_type=1)
    return Response(status=204)


@bp.route('/')
def index():
    # границы данных и текущая дата SM
    processor = DATA_PROCESSOR.get('sm')()
    sm_date_from, sm_date_to, sm_date_curr = processor.get_data_borders_and_current_date()
    # границы данных и текущая дата CDV
    processor = DATA_PROCESSOR.get('cdv')()
    cdv_date_from, cdv_date_to, cdv_date_curr = processor.get_data_borders_and_current_date()
    return render_template(
        'index.html',
        sm_df=sm_date_from,
        sm_dt=sm_date_to,
        sm_curr=sm_date_curr,
        cdv_df=cdv_date_from,
        cdv_dt=cdv_date_to,
        cdv_curr=cdv_date_curr
    )


@bp.route('/get_token', methods=['GET'])
def get_token():
    return render_template('get_token.html')


@bp.route('/arrival_sync', methods=['GET'])
def arrival_sync():
    app = current_app._get_current_object()
    waiting_for_arrival(app=app, branch='swissmedica')
    return render_template('arrival_sync.html')


@bp.route('/swissmedica_org_lead', methods=['POST', 'GET'], strict_slashes=False)
def swissmedica_org_lead():
    """ Пробрасывавет в AMO лиды с сайта swissmedica.org """
    """
    {
        'Name': 'test - please ignore',
        'Clients_Country': 'Georgia',
        'Email': 'Kir@swissmedica21.com',
        'Phone': '591058618',
        'Please_describe_your_problem': 'test - please ignore',
        'Checkbox': 'yes',
        'LP4_EN': 'LP4_EN',
        'tranid': '725354:5774608671',
        'COOKIES': ' _fbp=fb.1.1692261723692.1607646662; _ym_uid=1692261724710250210; _ym_d=1692261724; tildauid=1692261725123.513957; _gcl_au=1.1.523246661.1701948890; rerf=AAAAAGW6VFwObn+DAzEeAg==; _gid=GA1.2.164053568.1706710111; _ym_isad=2; _ym_visorc=w; tildasid=1706765241461.327595; _uetsid=fb0967f0c04211ee83e401378e0b8d50; _uetvid=fb098570c04211eeaed7851553f3f724; _gat_gtag_UA_148716138_1=1; _ga=GA1.1.601091886.1692261724; previousUrl=swissmedica.org%2Finnovative-therapy; _ga_XXMR2575TF=GS1.1.1706765238.15.1.1706769087.31.0.0',
        'formid': 'form480544796'
    }
    """
    # config = Config().swissmewdica_org_forms
    data: Dict = request.json
    print('swissmedica_org_lead', data)
    # определяем идентификатор формы
    # cookies = data.get('COOKIES')       # здесь приходит строка!!
    # form_id = data.get('formid')
    # form_config = config.get(form_id) or {}
    # записываем данные в google-таблицу
    append_form_data_to_google_sheets(form_data={
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source': f"swissmedica.org {data.get('Clients_Country') or ''}".strip(),
        'name': data.get('Name') or data.get('name') or '',
        'phone': data.get('Phone') or data.get('phone') or '',
        'email': data.get('Email') or data.get('email') or '',
        'msg': data.get('Please_describe_your_problem') or ''
    })
    # # для части форм сделки в Amo не создаем (флаг 'l' != 1)
    # if not form_config or form_config['l'] != 1:
    #     print('swissmedica_org_lead config error')
    #     return Response(status=200)
    # create_lead_based_on_form_data(
    #     lang=form_config['r'],  # регион / язык, ключ "r"
    #     ip=data.get('ip'),
    #     headers=dict(request.headers) or {},        # тут есть сомнения насчет формата
    #     name=data.get('Name'),
    #     phone=clear_phone(data.get('Phone') or ''),
    #     email=data.get('Email') or '',
    #     diagnosis=data.get('Please_describe_your_problem') or '',
    #     country_=data.get('Clients_Country')
    # )
    return Response(status=200)


@bp.route('/startstemcells_lead', methods=['POST', 'GET'], strict_slashes=False)
def startstemcells_lead():
    """ Пробрасывавет в AMO лиды с сайта startstemcells.com """
    config = Config().startstemcells_forms
    data: Dict = request.json
    form_data = data.get('post') or {}
    print('startstemcells_lead', form_data)
    # определяем идентификатор формы
    form_id = form_data.get('_hf_form_id')
    form_config = config.get(form_id) or {}
    # записываем данные в google-таблицу
    append_form_data_to_google_sheets(form_data={
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source': f"startstemcells {form_config.get('r') or ''}".strip(),
        'name': form_data.get('name') or '',
        'phone': form_data.get('phone') or '',
        'email': form_data.get('email') or '',
        'msg': form_data.get('diagnosis') or form_data.get('message') or form_data.get('msg') or ''
    })
    # проверяем лид на спам
    is_spam = False
    phone = clear_phone(form_data.get('phone') or '')
    email = form_data.get('email') or ''
    msg = form_data.get('diagnosis') or form_data.get('message') or form_data.get('msg') or ''
    try:
        is_spam = LeadsInsurance(branch='swissmedica').is_spam(line={'phone': phone, 'email': email, 'msg': msg})
    except Exception as exc:
        print('failed to perform spam check', exc)
    if is_spam:
        print('spam lead detected')
        return Response(status=200)
    # для части форм сделки в Amo не создаем (флаг 'l' != 1)
    if not form_config or form_config['l'] != 1:
        print('startstemcells_lead config error')
        return Response(status=200)
    utm_dict = {
        'utm_source': form_data.get('utm_source') or '',
        'utm_medium': form_data.get('utm_medium') or '',
        'utm_campaign': form_data.get('utm_campaign') or '',
        'utm_content': form_data.get('utm_content') or '',
        'utm_term': form_data.get('utm_term') or '',
        'referer': form_data.get('referer') or '',
        'ym_cid': form_data.get('ym_cid') or '',
        'lead_url': form_data.get('lead_url') or ''
    }
    create_lead_based_on_form_data(
        lang=form_config['r'],  # регион / язык, ключ "r"
        ip=data.get('ip') or (data.get('location') or {}).get('ip'),
        headers=data.get('headers') or {},
        cookies=data.get('cookies') or {},
        name=form_data.get('name'),
        phone=phone,
        email=email,
        diagnosis=msg,
        utm_dict=utm_dict
    )
    return Response(status=200)


def append_form_data_to_google_sheets(form_data):
    if len(form_data) != 6:
        return
    for key in ('date', 'source', 'name', 'phone', 'email', 'msg'):
        if key not in form_data:
            return
    try:
        GoogleAPIClient(
            book_id=GoogleSheets.LeadsFromSites.value,
            sheet_title='Leads'
        ).add_row(form_data)
    except Exception as exc:
        print(exc)


def create_lead_based_on_form_data(
    lang: str,
    ip: str,
    headers: Dict,
    cookies: Dict,
    name: str,
    phone: str,
    email: str,
    diagnosis: str,
    country_: Optional[str] = None,
    utm_dict: Optional[Dict] = None
):
    referer = headers.get('Referer') or ''
    origin = headers.get('Origin') or headers.get('origin') or ''
    site = origin.replace('https://', '').replace('http://', '')
    country_data = get_country_by_ip(ip=ip) if ip else {}
    country, city = country_data.get('country'), country_data.get('city')
    # если страну по ip не определили, но она указана явно
    if not country and country_:
        country = country_
    if not utm_dict:
        utm_dict = get_args_from_url(url=referer) if referer else {}
    spoken_language = {'EN': 'English', 'DE': 'German', 'FR': 'French', 'IT': 'Italian'}
    custom_fields_values = [
        # Spoken language
        {"field_id": 1099051, "values": [{"value": spoken_language.get(lang) or 'Another'}]},
        # Country_from_Jivo
        {"field_id": 976545, "values": [{"value": country}]},
        # City_from_Jivo
        {"field_id": 976549, "values": [{"value": city}]},
        # Disease if other
        {"field_id": 957691, "values": [{"value": diagnosis}]},
        # идентификатор яндекс-метрики
        # {"field_id": 1102815, "values": [{"value": cookies.get('_ym_uid') or cookies.get('_YM_UID')}]},
    ]
    # идентификаторы сущностей в Amo: p - pipeline, s - status, t - tag
    amo_ids = {
        'EN': {'p': 772717, 's': 19045762, 't': 689047},
        'DE': {'p': 2048428, 's': 29839168, 't': 689049},
        'FR': {'p': 2047060, 's': 29830081, 't': 689053},
        'IT': {'p': 5707270, 's': 50171236, 't': 689051},
        # пока что проброс в английскую воронку
        'CZ': {'p': 772717, 's': 19045762, 't': 689055}
    }
    # пустым конфиг не будет, по умолчанию всегда английская воронка
    amo_config = amo_ids.get(lang) or amo_ids.get('EN')
    amo_client = SwissmedicaAPIClient()
    # проверка на дубли
    # existing_leads = []
    # if phone:
    #     existing_leads = list(amo_client.find_leads(query=phone, limit=1))
    # if not existing_leads and email:
    #     existing_leads = list(amo_client.find_leads(query=email, limit=1))
    # lead_id = int(existing_leads[0]['id']) if existing_leads else None
    # if lead_id:
    #     # лид уже существует, отправим оповещение о том, что он попытался выйти на связь
    #     pass
    #     return Response(status=200)
    # добавляем лид
    response = amo_client.add_lead_simple(
        title=f"{name} :: {site}",
        name=name,
        pipeline_id=amo_config['p'],
        status_id=amo_config['s'],
        contacts=[
            {'value': phone, 'field_id': 771220, 'enum_code': 'WORK'},
            {'value': email, 'field_id': 771222, 'enum_code': 'WORK'},
        ],
        tags=[{'id': amo_config['t']}],
        utm=utm_dict,
        referer=referer,
        custom_fields_values=custom_fields_values,
        responsible_user_id=0
    )
    print('lead creation result', response.status_code, response.text)


@bp.route('/cellulestaminali_lead', methods=['POST', 'GET'], strict_slashes=False)
def cellulestaminali_lead():
    data: Dict = request.json
    form_data = data.get('post') or {}
    # записываем данные в google-таблицу
    append_form_data_to_google_sheets(form_data={
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source': f"cellulestaminali {'IT'}".strip(),
        'name': form_data.get('name') or '',
        'phone': form_data.get('phone') or '',
        'email': form_data.get('email') or '',
        'msg': form_data.get('message') or ''
    })
    # проверяем лид на спам
    is_spam = False
    phone = clear_phone(form_data.get('phone') or '')
    email = form_data.get('email') or ''
    msg = form_data.get('diagnosis') or form_data.get('message') or form_data.get('msg') or ''
    try:
        is_spam = LeadsInsurance(branch='swissmedica').is_spam(line={'phone': phone, 'email': email, 'msg': msg})
    except Exception as exc:
        print('failed to perform spam check', exc)
    if is_spam:
        print('spam lead detected')
        return Response(status=200)
    utm_dict = {
        'utm_source': form_data.get('utm_source') or '',
        'utm_medium': form_data.get('utm_medium') or '',
        'utm_campaign': form_data.get('utm_campaign') or '',
        'utm_content': form_data.get('utm_content') or '',
        'utm_term': form_data.get('utm_term') or '',
        'referer': form_data.get('referer') or '',
        'ym_cid': form_data.get('ym_cid') or '',
        'lead_url': form_data.get('lead_url') or ''
    }
    create_lead_based_on_form_data(
        lang='IT',  # регион / язык, ключ "r"
        ip=data.get('ip'),
        headers=data.get('headers') or {},
        cookies=data.get('cookies') or {},
        name=form_data.get('name'),
        phone=phone,
        email=email,
        diagnosis=msg,
        utm_dict=utm_dict
    )
    return Response(status=200)


@bp.route('/add_lead_from_cf', methods=['POST', 'GET'], strict_slashes=False)
def add_lead_from_cf():
    # http://167.172.109.78/calltracking3/?lang=FR
    # https://swiss-medica-2e0e7bc937df.herokuapp.com/add_lead_from_cf/?lang=FR
    # https://swiss-medica-2e0e7bc937df.herokuapp.com/add_lead_from_cf/?lang=IT
    # https://swiss-medica-2e0e7bc937df.herokuapp.com/add_lead_from_cf/?lang=DE
    # https://swiss-medica-2e0e7bc937df.herokuapp.com/add_lead_from_cf/?lang=CZ
    # https://swiss-medica-2e0e7bc937df.herokuapp.com/add_lead_from_cf/?lang=EN
    return Response(status=200)

    # try:
    #
    #     post = request.form.to_dict()
    #     lang = request.args.get('lang', default='EN')  # Получаем язык из GET-параметров, по умолчанию 'EN'
    #     form_data = post
    #
    #     try:
    #         print('args', request.args.to_dict())
    #         print('headers', request.headers)
    #         print('cookies', request.cookies)
    #     except:
    #         pass
    #
    #     pipeline_ids = {'EN': 772717, 'DE': 2048428, 'FR': 2047060, 'IT': 5707270}
    #     status_ids = {'EN': 19045762, 'DE': 29839168, 'FR': 29830081, 'IT': 50171236}
    #     temptags = {'EN': 689047, 'DE': 689049, 'FR': 689053, 'IT': 689051, 'CZ': 689055}
    #
    #     form_data['pipeline_id'] = pipeline_ids.get(lang, 772717)
    #     form_data['status_id'] = status_ids.get(lang, 19045762)
    #     form_data['tags'] = [{"id": temptags.get(lang, 689057)}]
    #
    #     form_data['message'] = post.get('message', post.get('diagnosis', 'No message'))
    #
    #     if not form_data.get('name'):
    #         return "NO NAME", 400
    #
    #     parsed_url = urlparse(post.get('utm_referer', ''))
    #     getmass = parse_qs(parsed_url.query)
    #
    #     for key, value in getmass.items():
    #         form_data[key] = value[0][:250]
    #
    #     if 'utm_referer' in form_data:
    #         form_data['utm_referer'] = form_data['utm_referer'][:250]
    #
    #     form_data.setdefault('email', 'no email')
    #     form_data.setdefault('detected_country', 'not_detected_country')
    #     form_data.setdefault('detected_city', 'not_detected_city')
    #
    #     print(form_data)
    #     # вот это вообще от балды...
    #     utm_dict = {
    #         'utm_source': form_data.get('utm_source'),
    #         'utm_campaign': form_data.get('utm_campaign'),
    #         'utm_medium': form_data.get('utm_medium')
    #     }
    #     amo_client = SwissmedicaAPIClient()
    #     spoken_language = {'EN': 'English', 'DE': 'German', 'FR': 'French', 'IT': 'Italian'}
    #     custom_fields_values = [{"field_id": 1099051, "values": [{"value": spoken_language.get(lang) or 'Another'}]}]
    #     if form_data.get('diagnosis'):
    #         custom_fields_values.append({"field_id": 957691, "values": [{"value": form_data.get('diagnosis')}]})
    #     lead_added = amo_client.add_lead_simple(
    #         name=form_data['name'],
    #         pipeline_id=int(form_data['pipeline_id']),
    #         status_id=int(form_data['status_id']),
    #         contacts=[
    #             {'value': form_data.get('phone'), 'field_id': 771220, 'enum_code': 'WORK'},
    #             {'value': form_data.get('email'), 'field_id': 771222, 'enum_code': 'WORK'},
    #         ],
    #         tags=form_data['tags'],
    #         referer=form_data.get('utm_referer'),
    #         utm=utm_dict,
    #         custom_fields_values=custom_fields_values
    #     )
    #     added_lead_data = lead_added.json()
    #     try:
    #         lead_id = int(added_lead_data[0]['id'])
    #         note_text = ''
    #         for k, v in form_data.items():
    #             if k in ('tags', ):
    #                 continue
    #             note_text = f"{note_text}\n{k.upper()} :: {v}"
    #         amo_client.add_note_simple(entity_id=lead_id, text=note_text.strip())
    #     except:
    #         pass
    #     # {
    #     #     'name': 'test me',
    #     #     'phone': '963258741',
    #     #     'diagnosis': 'sdfsdg',
    #     #     'email': 'Kirill.Mizonov@swissmedica21.com',
    #     #     'agree': 'on',
    #     #     'clientid': '864083159.1695878461',
    #     #     'pipeline_id': 2047060,
    #     #     'status_id': 29830081,
    #     #     'tags': [{'id': 689053}],
    #     #     'message': 'sdfsdg',
    #     #     'detected_country': 'not_detected_country',
    #     #     'detected_city': 'not_detected_city'
    #     # }
    #
    # except Exception as exc:
    #     print('error', exc)
    #
    # return Response(status=200)


@bp.route('/get_token', methods=['POST'])
def send_auth_code():
    auth_code = request.form.get('auth_code')
    client_id = request.form.get('client_id')
    client_secret = request.form.get('client_secret')
    redirect_url = request.form.get('redirect_url')
    branch = request.form.get('branch')
    # записываем креды в БД
    with current_app.app_context():
        api_client = API_CLIENT.get(branch)()
        api_client.get_token(
            auth_code=auth_code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_url=redirect_url,
        )
    return redirect(url_for('main.get_token'))


# class DateTimeDecoder(json.JSONDecoder):
#     def __init__(self, *args, **kwargs):
#         json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)
#
#     def object_hook(self, dct):
#         for k, v in dct.items():
#             if isinstance(v, str):
#                 try:
#                     dct[k] = datetime.fromisoformat(v)
#                 except ValueError:
#                     try:
#                         dct[k] = date.fromisoformat(v)
#                     except ValueError:
#                         pass
#         return dct


def data_to_excel(branch: str):

    model = DATA_MODEL.get(branch)
    portion_size = 1000
    offset = 0
    # print(f'sending {branch} pivot data started')
    socketio.emit('pivot_data', {
        'start': True,
        'data': [],
        'headers': None,
        'done': False,
        'file_name': None
    })
    num = 0
    headers = []
    while True:
        collection = model.query.limit(portion_size).offset(offset).all()
        if not collection:
            break
        if not headers:
            headers = [x for x in collection[0].to_dict().get('data').keys()]
            # print(f'headers: {headers} ')
        data = [
            x.to_dict().get('data')
            for x in collection
        ]
        num += 1
        # print(f'sending {branch} pivot data [{num} :: {len(data)}]')
        if len(data) > 0:
            print('sending', data[0]['pipeline_name'])
        socketio.emit('pivot_data', {
            'start': False,
            'data': data,
            'headers': headers,
            'done': False,
            'file_name': None
        })
        offset += portion_size
    # print(f'sending {branch} pivot data stopped')
    socketio.emit('pivot_data', {
        'start': False,
        'data': [],
        'headers': headers,
        'done': True,
        'file_name': f'data_{branch}'
    })
    return Response(status=204)


@bp.route('/data_excel_sm')
def data_to_excel_sm():
    return data_to_excel(branch='sm')


@bp.route('/data_excel_cdv')
def data_to_excel_cdv():
    # collection = CDVData.query.all()
    # data = [(x.to_dict() or {}).get('data') for x in collection]
    # ExcelClient(file_path=os.path.join('app', 'data'), file_name='data_cdv').write(data=[
    #     ExcelClient.Data(data=data)
    # ])
    # return send_file(os.path.join('data', 'data_cdv.xlsx'), as_attachment=True)
    return data_to_excel(branch='cdv')


@bp.route('/new_raw_lead', methods=['POST'])
def new_raw_lead():
    """ В Amo пришел новый лид, его данные необходимо записать в RawLeadData """
    data = get_data_from_post_request(_request=request)
    if not data:
        return 'Unsupported Media Type', 415
    lead_id = data.get('leads[add][0][id]')
    if not lead_id:
        return Response(status=204)
    branch = data.get('account[subdomain]')
    # вытаскиваем данные сделки и контакта
    amo_client = API_CLIENT.get(branch)()
    lead = amo_client.get_lead_by_id(lead_id=lead_id) or {}
    contacts = (lead.get('_embedded') or {}).get('contacts')
    contact = amo_client.get_contact_by_id(contact_id=contacts[0]['id']) if contacts else {}
    # добавляем запись в RawLeadData
    raw_lead_model: Type[Union[SMRawLeadData, CDVRawLeadData]] = RAW_LEAD.get(branch)
    app = current_app._get_current_object()
    with app.app_context():
        raw_lead_model.add(
            id_on_source=lead['id'],
            created_at=lead['created_at'],
            updated_at=lead['updated_at'],
            data=DateTimeEncoder.encode({
                'lead': lead,
                'contact': contact
            })
        )
    return Response(status=204)


@bp.route('/get_amo_data_sm')
def get_amo_data_sm():
    return start_get_data_from_amo_scheduler(branch='sm')


@bp.route('/amo_chat/<scope_id>', methods=['POST'])
def amo_chat(scope_id):
    """ Пришло сообщение из Amo Chat:
        менеджер через интерфейс Amo написал клиенту - нам нужно переслать сообщение в WhatsApp
        Формат данных:
            {'account_id': '59a2fb56-7492-4c16-8bbe-f776345af46c', 'time': 1700951116, 'message': {'receiver': {'id': '8cab93ac-a6cc-40c7-9021-989ae3629bb1', 'name': 'Kirill Mizonow', 'phone': '995591058618', 'client_id': '995591058618'}, 'sender': {'id': 'ab8317cd-eb38-4bf4-8462-47a4b328a887', 'name': 'Василий Админ'}, 'conversation': {'id': '988b9688-e8b9-47ed-8eb8-2339dffd4f17', 'client_id': 'cc5d7525-6e8d-4cd1-8ace-e09900e88ea1'}, 'timestamp': 1700951116, 'msec_timestamp': 1700951116276, 'message': {'id': '527af4d5-2a69-48b2-87f0-b665f4bd2b9c', 'type': 'text', 'text': 'should work', 'markup': None, 'tag': '', 'media': '', 'thumbnail': '', 'file_name': '', 'file_size': 0}}}
    Args:
        scope_id: идентификатор, позволяющий судить о том, с какого аккаунта Amo прилетели данные
    """
    # print('got info from AMO Chat', scope_id, request.json)
    data = request.json
    message = data.get('message')
    if not message:
        return Response(status=204)
    receiver = message['receiver']['phone']
    msg = message['message']['text']
    # по scope_id определяем аккаунт
    for branch, config in Config().amo_chat.items():
        if config.get('scope_id') == scope_id:
            # будет выбран первый номер из списка (переменная WHATSAPP) для данного филиала
            WhatsAppController(branch=branch).send_message(number_to=receiver, message=msg)
            break
    return Response(status=204)


@bp.route('/get_amo_data_cdv')
def get_amo_data_cdv():
    return start_get_data_from_amo_scheduler(branch='cdv')


@bp.route('/tawk', methods=['POST'])
def tawk():
    return TawkController().handle(request=request)


@bp.route('/stop_get_amo_data_sm')
def stop_get_amo_data_sm():
    return stop_get_data_from_amo_scheduler(branch='sm')


@bp.route('/stop_get_amo_data_cdv')
def stop_get_amo_data_cdv():
    return stop_get_data_from_amo_scheduler(branch='cdv')


@bp.route('/start_update_pivot_data_sm')
def start_update_pivot_data_sm():
    return start_update_pivot_data(branch='sm')


@bp.route('/start_update_pivot_data_cdv')
def start_update_pivot_data_cdv():
    return start_update_pivot_data(branch='cdv')


@bp.route('/stop_update_pivot_data_sm')
def stop_update_pivot_data_sm():
    return stop_update_pivot_data(branch='sm')


@bp.route('/stop_update_pivot_data_cdv')
def stop_update_pivot_data_cdv():
    return stop_update_pivot_data(branch='cdv')


@bp.route('/create_all')
def create_all():
    # импорты нужны для создания структуры БД!
    from app.models.amo_credentials import CDVAmoCredentials, SMAmoCredentials
    from app.models.amo_token import SMAmoToken, CDVAmoToken
    from app.models.contact import SMContact, CDVContact
    from app.models.event import SMEvent, CDVEvent
    from app.models.lead import CDVLead, SMLead
    from app.models.note import SMNote, CDVNote
    from app.models.pipeline import CDVPipeline, SMPipeline
    from app.models.user import SMUser, CDVUser
    from app.models.task import SMTask, CDVTask
    from app.models.company import SMCompany, CDVCompany
    from app.models.data import SMData, CDVData
    from app.models.log import SMLog, CDVLog
    from app.models.autocall import SMAutocallNumber, CDVAutocallNumber
    from app.models.chat import SMChat, CDVChat
    from app.models.raw_lead_data import SMRawLeadData, CDVRawLeadData
    with current_app.app_context():
        db.create_all()
    return 'tables created'


@bp.route('/drop_all')
def drop_all():
    with current_app.app_context():
        db.drop_all()
    return 'tables dropped'
