var globalData = null; // Глобальная переменная для хранения данных

document.addEventListener('DOMContentLoaded', function() {
  fetchDataFromBackend(); // Функция для получения данных с бэкенда
});

function fetchDataFromBackend() {
  fetch('http://127.0.0.1:5000/load_offer_data')
    .then(response => response.json())
    .then(data => {
      globalData = data; // Сохранение полученных данных в глобальной переменной
      populateList('template');
      populateList('advisor');
      populateList('language');
      populateList('clinic');
      populateList('diagnosis');
      populateList('therapy_type');
    })
    .catch(error => console.error('Ошибка:', error));
}

function populateList(dataKey, selectedTherapyTypeId = null) {
	console.log(dataKey, selectedTherapyTypeId)
  const listElement = document.getElementById(dataKey);
  listElement.innerHTML = ''; // Очистка текущего списка
  const defaultOption = document.createElement('option');
  defaultOption.textContent = '< select >';
  defaultOption.value = '';
  listElement.appendChild(defaultOption);

  const uniqueTitles = new Set();

  globalData[dataKey].forEach(item => {
    const therapyTypeIds = item.therapy_type ? item.therapy_type.split(", ").map(Number) : [];
    if ((selectedTherapyTypeId === null || therapyTypeIds.includes(parseInt(selectedTherapyTypeId))) && !uniqueTitles.has(item.title)) {
      uniqueTitles.add(item.title);
      const option = document.createElement('option');
      option.value = item.id;
      option.textContent = item.title;
      listElement.appendChild(option);
    }
  });
}

// Обработчики событий для списков
document.getElementById('therapy_type').addEventListener('change', function() {
  const selectedTherapyTypeId = this.value;
  populateList('type_of_administration', selectedTherapyTypeId);
  populateList('examination_package', selectedTherapyTypeId);
  populateList('active_substance', selectedTherapyTypeId);
  populateList('physiotherapy', selectedTherapyTypeId);
});

document.getElementById('add_procedure').addEventListener('click', function() {
	// Определяем выбранный класс процедуры и идентификатор
    const procedureClasses = ['type_of_administration', 'examination_package', 'active_substance', 'physiotherapy'];
    let selectedClass = '';
    let selectedProcedureId = '';
    procedureClasses.forEach(pc => {
        const selectElement = document.getElementById(pc);
        if (selectElement && selectElement.value && selectElement.value !== '<select>') {
            selectedClass = pc;
            selectedProcedureId = selectElement.value;
        }
    });

    // Если не выбран класс процедуры, прерываем выполнение
    if (!selectedClass) return;

    const quantity = parseInt(document.getElementById('procedure_quantity').value, 10);
    const selectedProcedure = globalData[selectedClass].find(item => item.id === selectedProcedureId);
    if (!selectedProcedure) return;

    // Создаем строку таблицы для каждой процедуры
    const tr = document.createElement('tr');
    tr.dataset.id = selectedProcedureId;
    tr.dataset.class = selectedClass;

    // Название процедуры
    const tdTitle = document.createElement('td');
    tdTitle.textContent = selectedProcedure.title;
    tr.appendChild(tdTitle);

    // Цена процедуры
    const tdPrice = document.createElement('td');
    tdPrice.textContent = selectedProcedure.price || '-';
    tdPrice.style.width = '100px'; // Фиксированная ширина для столбца цены
    tr.appendChild(tdPrice);

    // Количество
    const tdQuantity = document.createElement('td');
    const inputQuantity = document.createElement('input');
    inputQuantity.type = 'number';
    inputQuantity.value = quantity;
    inputQuantity.min = '1';
    inputQuantity.className = 'procedure-quantity';
    inputQuantity.style.width = '50px'; // Фиксированная ширина для поля количества
    tdQuantity.appendChild(inputQuantity);
    tr.appendChild(tdQuantity);

    // Кнопка удаления
    const tdDelete = document.createElement('td');
    const buttonDelete = document.createElement('button');
    buttonDelete.textContent = 'x';
    buttonDelete.className = 'delete-procedure';
    buttonDelete.style.width = '30px'; // Фиксированная ширина для кнопки удаления
    buttonDelete.addEventListener('click', function() {
        tr.remove();
    });
    tdDelete.appendChild(buttonDelete);
    tr.appendChild(tdDelete);

    // Добавляем строку в таблицу корзины
    document.getElementById('selected_procedures').appendChild(tr);
});

document.getElementById('load_offer').addEventListener('click', function() {
    const selectedTemplateTitle = document.getElementById('template').options[document.getElementById('template').selectedIndex].text;
    if (!selectedTemplateTitle || selectedTemplateTitle === "<select>") return;

    // Очищаем корзину
    const selectedProceduresList = document.getElementById('selected_procedures');
    selectedProceduresList.innerHTML = '';

    // Находим все записи с выбранным шаблоном оффера
    const selectedTemplates = globalData['template'].filter(t => t.title === selectedTemplateTitle);

    selectedTemplates.forEach(procedure => {
        // Добавляем каждую процедуру, связанную с шаблоном, в корзину
        const procedureClasses = ['type_of_administration', 'active_substance', 'physiotherapy', 'examination_package'];
        procedureClasses.forEach(procClass => {
            const procedureId = procedure[procClass];
            if (procedureId) {
                const procedureData = globalData[procClass]?.find(p => p.id === procedureId);
                if (procedureData) {
                    const listElement = document.createElement('li');
                    listElement.innerHTML = `${procedureData.title} - Quantity: <input type='number' value='${procedure.quantity || 1}' min='1' class='procedure-quantity' /> <button class='delete-procedure'>Delete</button>`;
                    listElement.dataset.id = procedureData.id;
                    listElement.dataset.class = procClass;

                    // Обработчик удаления процедуры из списка
                    listElement.querySelector('.delete-procedure').addEventListener('click', function() {
                        listElement.remove();
                    });

                    selectedProceduresList.appendChild(listElement);
                }
            }
        });
    });
});

async function handleOffer(action) {
    const procedures = Array.from(document.querySelectorAll('#selected_procedures li')).map(li => ({
        id: li.dataset.id,
        class: li.dataset.class,
        quantity: parseInt(li.querySelector('.procedure-quantity').value, 10)
    }));

    // Определяем URL на основе действия
    const url = action === 'Save' ? '/save_offer' : '/build_offer';

    try {
        const response = await fetch(url, {
            method: 'POST', // или 'PUT'
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({procedures}), // Преобразуем данные в строку JSON
        });

        if (!response.ok) {
            throw new Error('Network response was not ok');
        }

        const jsonResponse = await response.json(); // Парсим JSON-ответ от сервера

        // Обрабатываем ответ от сервера
        document.getElementById('user_messages').textContent = jsonResponse.message; // Предполагаем, что сервер возвращает сообщение в поле message
    } catch (error) {
        console.error('Ошибка:', error);
        document.getElementById('user_messages').textContent = 'Произошла ошибка при обработке вашего запроса.';
    }
}

document.getElementById('save_offer').addEventListener('click', () => handleOffer('Save'));
document.getElementById('build_offer').addEventListener('click', () => handleOffer('Build'));

document.getElementById('clear_procedures').addEventListener('click', function() {
    document.getElementById('selected_procedures').innerHTML = ''; // Очищаем список
});

document.addEventListener('DOMContentLoaded', function() {
    // Находим все заголовки секций, которые будут работать как кнопки для сворачивания/разворачивания
    const collapsibleHeaders = document.querySelectorAll('.collapsible-header');

    collapsibleHeaders.forEach(header => {
        header.addEventListener('click', function() {
            // Находим ближайший родительский элемент с классом collapsible-container
            const container = this.closest('.collapsible-container');
            const content = container.querySelector('.collapsible-content');
            // Переключаем класс is-open для анимации и изменения высоты
            content.classList.toggle('is-open');
        });
    });

  const quantityInput = document.getElementById('procedure_quantity');

  document.querySelector('.quantity-minus').addEventListener('click', function () {
    if (quantityInput.value > parseInt(quantityInput.min)) {
      quantityInput.value = parseInt(quantityInput.value) - 1;
    }
  });

  document.querySelector('.quantity-plus').addEventListener('click', function () {
    quantityInput.value = parseInt(quantityInput.value) + 1;
  });
});