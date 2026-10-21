"""
预警模块：价格预警 + ML信号预警 + 绩效预警
"""
import json
import os
from datetime import datetime

ALERT_FILE = os.path.join(os.path.dirname(__file__), 'alerts.json')

def load_alerts():
    if os.path.exists(ALERT_FILE):
        with open(ALERT_FILE) as f:
            return json.load(f)
    return {'price_alerts': [], 'ml_alerts': [], 'performance_alerts': []}

def save_alerts(data):
    with open(ALERT_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def check_price_alert(current_price, threshold_pct=0.03, symbol='default'):
    """
    价格预警：当日价格波动超过 threshold_pct（默认3%）时触发
    返回预警列表
    """
    alerts_db = load_alerts()
    new_alerts = []

    # 读取最后K线做对比
    from core.data import fetch_a_stock_data
    df = fetch_a_stock_data(symbol, start_date='20260101', end_date='20260713')
    if df is not None and len(df) > 1:
        close_col = '收盘' if '收盘' in df.columns else 'Close'
        prev_close = df[close_col].iloc[-2]
        change = (current_price - prev_close) / prev_close
        if abs(change) > threshold_pct:
            alert = {
                'type': 'price',
                'time': datetime.now().isoformat(),
                'price': float(current_price),
                'change': f"{change:.2%}",
                'threshold': f"{threshold_pct:.0%}",
                'message': f"⚠️ 价格波动 {change:.2%}，超过阈值 {threshold_pct:.0%}"
            }
            new_alerts.append(alert)
            alerts_db['price_alerts'].append(alert)
            print(alert['message'])

    save_alerts(alerts_db)
    return new_alerts

def check_ml_signal_alert(signal, probability, symbol='default'):
    """
    ML信号预警：当ML发出强信号时提醒
    signal: 1买入, -1卖出, 0持有
    probability: 预测概率
    """
    alerts_db = load_alerts()
    new_alerts = []

    if signal != 0 and probability > 0.7:
        direction = "买入" if signal == 1 else "卖出"
        alert = {
            'type': 'ml_signal',
            'time': datetime.now().isoformat(),
            'signal': direction,
            'probability': f"{probability:.1%}",
            'symbol': symbol,
            'message': f"🔔 {symbol} ML强信号: {direction} (概率 {probability:.1%})"
        }
        new_alerts.append(alert)
        alerts_db['ml_alerts'].append(alert)
        print(alert['message'])

    save_alerts(alerts_db)
    return new_alerts

def check_performance_alert(summary):
    """
    绩效预警：当回测绩效触及阈值时提醒
    """
    alerts_db = load_alerts()
    new_alerts = []

    try:
        total_ret = float(summary.get('总收益率', '0%').strip('%')) / 100
        max_dd = float(summary.get('最大回撤', '0%').strip('%')) / 100
    except Exception as e:
        print(f"⚠️ 绩效数据解析失败：{e}")
        return []

    if max_dd < -0.15:
        alert = {
            'type': 'performance',
            'time': datetime.now().isoformat(),
            'max_drawdown': f"{max_dd:.2%}",
            'message': f"🚨 最大回撤 {max_dd:.2%}，超过15%警戒线！建议暂停策略或调整参数"
        }
        new_alerts.append(alert)
        alerts_db['performance_alerts'].append(alert)
        print(alert['message'])

    if len(alerts_db['performance_alerts']) > 0:
        last = alerts_db['performance_alerts'][-1]
        latest_ret = total_ret
        if latest_ret > 0.20:
            alert = {
                'type': 'performance',
                'time': datetime.now().isoformat(),
                'return': f"{latest_ret:.2%}",
                'message': f"💰 累计收益 {latest_ret:.2%}，达到20%目标！"
            }
            new_alerts.append(alert)
            alerts_db['performance_alerts'].append(alert)
            print(alert['message'])

    save_alerts(alerts_db)
    return new_alerts

def show_recent_alerts(n=5):
    """显示最近n条预警"""
    alerts_db = load_alerts()
    all_alerts = []
    for category in alerts_db.values():
        all_alerts.extend(category)
    all_alerts.sort(key=lambda x: x.get('time', ''), reverse=True)

    print(f"\n📋 最近预警 ({len(all_alerts[:n])}条):")
    for a in all_alerts[:n]:
        print(f"  [{a.get('time','')[:19]}] {a.get('message','')}")

if __name__ == '__main__':
    check_price_alert(52.5, threshold_pct=0.03)
    check_ml_signal_alert(1, 0.85)
    show_recent_alerts()
