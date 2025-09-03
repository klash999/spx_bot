import requests
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from datetime import datetime
import telegram
import schedule
import time
import csv

# إعدادات ثابتة
api_key = '0uEg3krvSTKrmZOhegx7l1YwVAIt9vEK'
bot_token = '8016056055:AAG7CpxRS2OaQIq-QtqYu99xE6zgZddMJBA'
chat_id = '1793820239'
symbol = 'SPXW'
limit = 100

# دالة تسجيل الإشارات
def log_signal(option):
    with open('signals_log.csv', 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now(),
            option['strike'],
            option['type'],
            option['last_price'],
            option['delta'],
            option['iv']
        ])

# دالة تشغيل البوت
def run_bot():
    today = datetime.today().strftime('%Y-%m-%d')
    bot = telegram.Bot(token=bot_token)

    # جلب سلسلة الخيارات اليومية
    chain_url = f'https://api.polygon.io/v3/reference/options/contracts?underlying_ticker={symbol}&expiration_date={today}&limit={limit}&apiKey={api_key}'
    try:
        chain_response = requests.get(chain_url).json()
        contracts = chain_response.get('results', [])
    except Exception as e:
        bot.send_message(chat_id=chat_id, text=f"❌ خطأ في جلب العقود: {e}")
        return

    options_data = []

    # جلب بيانات كل عقد
    for contract in contracts:
        contract_id = contract['contract_id']
        details_url = f'https://api.polygon.io/v3/snapshot/options/{contract_id}?apiKey={api_key}'
        try:
            details_response = requests.get(details_url).json()
            option = details_response['results']
            greeks = option['greeks']
            quote = option['last_quote']
            options_data.append({
                'strike': option['details']['strike_price'],
                'type': option['details']['type'],
                'delta': greeks['delta'],
                'gamma': greeks['gamma'],
                'theta': greeks['theta'],
                'vega': greeks['vega'],
                'iv': option['implied_volatility'],
                'last_price': quote['last_price']
            })
        except Exception as e:
            print(f"⚠️ خطأ في العقد {contract_id}: {e}")
            continue

    # تحويل البيانات إلى جدول
    df = pd.DataFrame(options_data).dropna()
    if df.empty:
        bot.send_message(chat_id=chat_id, text="⚠️ لم يتم العثور على بيانات خيارات SPX اليوم.")
        return

    # تحليل الاتجاه اللحظي
    df['trend'] = df['delta'].apply(lambda x: 1 if x > 0.5 else 0)

    # تدريب نموذج XGBoost
    X = df[['delta', 'gamma', 'theta', 'vega', 'iv']]
    y = df['trend']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

    model = xgb.XGBClassifier()
    model.fit(X_train, y_train)

    # توقع الإشارات
    df['prediction'] = model.predict(X)
    top_options = df[df['prediction'] == 1].sort_values(by='delta', ascending=False).head(3)

    if top_options.empty:
        bot.send_message(chat_id=chat_id, text="📉 لا توجد إشارات تداول قوية حاليًا.")
        return

    # إرسال الإشارات وتسجيلها
    for _, option in top_options.iterrows():
        message = (
            f"🚨 توصية تداول SPX:\n"
            f"Strike: {option['strike']}\n"
            f"Type: {option['type']}\n"
            f"Price: {option['last_price']}\n"
            f"Delta: {option['delta']}\n"
            f"IV: {option['iv']}"
        )
        bot.send_message(chat_id=chat_id, text=message)
        log_signal(option)

# جدولة التشغيل كل 5 دقائق
schedule.every(5).minutes.do(run_bot)

# تشغيل مستمر
while True:
    schedule.run_pending()
    time.sleep(1)