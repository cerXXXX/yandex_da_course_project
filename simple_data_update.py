import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# конфигурация
DATA_PATH = '.\\data'
PLOTS_PATH = 'eda_plots'

VALID_DEVICES = ['android', 'ios', 'unknown']
VALID_EVENT_TYPES = [
    'login', 'logout', 'screen_view', 'button_click',
    'transaction', 'screen_view_popup'
]

sns.set_theme(style='whitegrid')


def load_data():
    # загрузка файлов из папки данных
    users = pd.read_csv(os.path.join(DATA_PATH, 'users_ab.csv'))
    events = pd.read_csv(os.path.join(DATA_PATH, 'events_ab.csv'))
    visits = pd.read_csv(os.path.join(DATA_PATH, 'visits_daily.csv'))
    return users, events, visits


def process_users_advanced(users: pd.DataFrame) -> pd.DataFrame:
    # очистка users
    users = users.copy()

    users['reg_date'] = pd.to_datetime(users.get('reg_date'), errors='coerce')

    users = users.drop_duplicates()
    users = users.drop_duplicates(subset=['user_id'], keep='first')

    users['age'] = pd.to_numeric(users.get('age'), errors='coerce')
    users = users[(users['age'] >= 14) & (users['age'] <= 100)].copy()

    min_valid_date = pd.Timestamp('2010-01-01')
    users = users[users['reg_date'].notna() & (users['reg_date'] >= min_valid_date)].copy()

    # нормализация device
    users['device'] = users.get('device').fillna('unknown').astype(str).str.lower().str.strip()
    users.loc[users['device'].str.contains('ios', na=False), 'device'] = 'ios'
    users.loc[users['device'].str.contains('android', na=False), 'device'] = 'android'
    users.loc[~users['device'].isin(['ios', 'android']), 'device'] = 'unknown'

    # нормализация city
    users['city'] = users.get('city').fillna('unknown').astype(str).str.strip().str.title()
    city_mapping = {'Нск': 'Новосибирск', 'Мск': 'Москва', 'Спб': 'Санкт-Петербург'}
    users['city'] = users['city'].replace(city_mapping)

    city_counts = users['city'].value_counts(normalize=True)
    small_cities = city_counts[city_counts < 0.01].index
    users.loc[users['city'].isin(small_cities), 'city'] = 'Прочие'

    print("---Завершена обработка users_ab.csv -> users_processed.csv---\n")
    return users


def process_events_logic(events: pd.DataFrame, users: pd.DataFrame) -> pd.DataFrame:
    # очистка events и формирование сессий
    events = events.copy()
    events['event_dt'] = pd.to_datetime(events.get('event_dt'), errors='coerce')

    # оставляем события только для известных пользователей
    df = users[['user_id']].merge(events, on='user_id', how='left')

    # корректность сумм
    if 'amount' in df.columns:
        df = df[df['amount'].isna() | (df['amount'] >= 0)].copy()

    # нормализация event_type
    if 'event_type' in df.columns:
        df['event_type'] = df['event_type'].astype(str).str.strip().str.lower()
        df = df[df['event_type'].isin(VALID_EVENT_TYPES)].copy()
    else:
        print("в events нет колонки 'event_type' — проверь файл")

    # сессии по разрыву >30 минут
    df = df.sort_values(['user_id', 'event_dt'])
    df['prev_time'] = df.groupby('user_id')['event_dt'].shift(1)
    df['time_diff'] = (df['event_dt'] - df['prev_time']).dt.total_seconds() / 60
    df['is_new_session'] = np.where((df['time_diff'] > 30) | (df['time_diff'].isna()), 1, 0)
    df['session_id'] = df.groupby('user_id')['is_new_session'].cumsum().astype(int)

    # удаляем logout как первое событие сессии (как аномалию)
    mask_invalid = (df['event_type'] == 'logout') & (df['is_new_session'] == 1)
    if mask_invalid.any():
        print(f"найдено {mask_invalid.sum()} аномальных logout-событий — удаляю")
        df = df[~mask_invalid].copy()

    print("---Завершена обработка events_ab.csv -> events_processed.csv---\n")
    return df


def process_visits(visits: pd.DataFrame) -> pd.DataFrame:
    # очистка visits
    visits = visits.copy()
    cols = list(visits.columns)
    if len(cols) >= 2:
        visits = visits.rename(columns={cols[0]: 'дата_события', cols[1]: 'visits'})

    if 'дата_события' in visits.columns:
        visits['дата_события'] = pd.to_datetime(visits['дата_события'], errors='coerce')

    visits = visits.drop_duplicates()

    if 'visits' in visits.columns:
        visits['visits'] = pd.to_numeric(visits['visits'], errors='coerce').fillna(0)
        visits = visits[visits['visits'] >= 0].copy()

    print("---Завершена обработка visits_ab.csv -> visits_processed.csv---\n")
    return visits


def perform_eda(users_clean: pd.DataFrame, events_clean: pd.DataFrame, plots_path: str):
    # базовый eda и сохранение графиков
    os.makedirs(plots_path, exist_ok=True)

    # возраст
    plt.figure()
    sns.histplot(data=users_clean, x='age', bins=20, kde=True)
    plt.title('распределение возраста пользователей')
    plt.xlabel('возраст')
    plt.savefig(os.path.join(plots_path, 'age_distribution.png'))
    plt.close()

    # города
    plt.figure(figsize=(10, 6))
    sns.countplot(data=users_clean, y='city',
                  order=users_clean['city'].value_counts().index)
    plt.title('пользователи по городам')
    plt.tight_layout()
    plt.savefig(os.path.join(plots_path, 'city_distribution.png'))
    plt.close()

    # устройства
    plt.figure()
    sns.countplot(data=users_clean, x='device',
                  order=users_clean['device'].value_counts().index)
    plt.title('пользователи по устройствам')
    plt.savefig(os.path.join(plots_path, 'device_distribution.png'))
    plt.close()

    # баланс групп a/b: цвет по device
    plt.figure(figsize=(8, 5))
    order = users_clean['group'].value_counts().index  # сохраняем порядок групп
    sns.countplot(data=users_clean, x='group', hue='device', order=order)
    plt.title('баланс групп a/b (цвет = device)')
    plt.legend(title='device', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(os.path.join(plots_path, 'group_balance_by_device.png'))
    plt.close()

    pivot = users_clean.groupby(['group', 'device']).size().unstack(fill_value=0)
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0)

    ax = pivot_pct.plot(kind='bar', stacked=True, figsize=(8, 5))
    ax.set_title('доля устройств внутри групп (stacked, %)')
    ax.set_ylabel('доля')
    ax.legend(title='device', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(os.path.join(plots_path, 'group_device_stacked.png'))
    plt.close()

    # баланс групп a/b: цвет по городу
    plt.figure(figsize=(10, 6))
    order = users_clean['city'].value_counts().index
    sns.countplot(data=users_clean, y='city', hue='group', order=order)
    plt.title('баланс групп A/B по городам')
    plt.legend(title='group', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(os.path.join(plots_path, 'group_balance_by_city.png'))
    plt.close()

    pivot = users_clean.groupby(['group', 'city']).size().unstack(fill_value=0)
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0)

    ax = pivot_pct.plot(kind='bar', stacked=True, figsize=(10, 6))
    ax.set_title('доля городов внутри групп (stacked, %)')
    ax.set_ylabel('доля')
    ax.legend(title='city', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(os.path.join(plots_path, 'group_city_stacked.png'))
    plt.close()

    # типы событий
    if 'event_type' in events_clean.columns:
        plt.figure(figsize=(10, 7))
        sns.countplot(data=events_clean, y='event_type',
                      order=events_clean['event_type'].value_counts().index)
        plt.title('типы событий')
        plt.tight_layout()
        plt.savefig(os.path.join(plots_path, 'event_type_distribution.png'))
        plt.close()

    print('графики сохранены в папку:', plots_path)


if __name__ == '__main__':
    users_raw, events_raw, visits_raw = load_data()

    users_clean = process_users_advanced(users_raw)
    events_clean = process_events_logic(events_raw, users_clean)
    visits_clean = process_visits(visits_raw)

    perform_eda(users_clean, events_clean, PLOTS_PATH)

    users_clean.to_csv('./data_processed/users_processed.csv', index=False)

    cols_to_save = ['user_id', 'event_dt', 'event_type', 'session_id']
    if 'amount' in events_clean.columns:
        cols_to_save.append('amount')
    if 'transaction_type' in events_clean.columns:
        cols_to_save.append('transaction_type')

    events_clean[cols_to_save].to_csv('./data_processed/events_processed.csv', index=False)
    visits_clean.to_csv('./data_processed/visits_processed.csv', index=False)

    print('✅ обработка завершена')
