#!/usr/bin/env python3
"""
诸暨市天气预报 — 多模型集合平均
Zhuji (29.72N, 120.23E)

今日逐时 (06~17时): 气温/体感/湿度/天气/降水
未来7天: 最高温/最低温/降水/天气
Models: ECMWF IFS + GFS + CMA GRAPES + GEM via Open-Meteo API
"""

import urllib.request, urllib.parse, json, sys
from datetime import datetime, timezone, timedelta

LAT, LON = 29.72, 120.23
CST = timezone(timedelta(hours=8))

MODELS = [
    ("ECMWF IFS", "ecmwf", 1.0),
    ("GFS",       "gfs",   1.0),
    ("CMA GRAPES","cma",   1.0),
    ("GEM",       "gem",   1.0),
]

HOUR_VARS = ["temperature_2m","apparent_temperature","relative_humidity_2m",
             "weather_code","precipitation"]
DAY_VARS  = ["temperature_2m_max","temperature_2m_min",
             "precipitation_sum","weather_code","wind_speed_10m_max"]

WMO = {0:"☀ 晴",1:"🌤 少云",2:"🌤 少云",3:"☁ 阴",
       45:"🌫 雾",48:"🌫 雾",
       51:"🌦 小雨",53:"🌦 小雨",55:"🌦 中雨",
       56:"🌧 冻雨",57:"🌧 冻雨",
       61:"🌧 雨",63:"🌧 雨",65:"🌧 大雨",
       66:"🌧 冻雨",67:"🌧 冻雨",
       71:"❄ 雪",73:"❄ 雪",75:"❄ 大雪",77:"❄ 雪粒",
       80:"🌧 阵雨",81:"🌧 阵雨",82:"🌧 暴雨",
       85:"❄ 阵雪",86:"❄ 阵雪",
       95:"⛈ 雷暴",96:"⛈ 雷暴+雹",99:"⛈ 雷暴+雹"}

def wmo_label(code):
    return WMO.get(code, "未知")

def fetch_model(ep):
    p = {"latitude":LAT, "longitude":LON,
         "hourly":",".join(HOUR_VARS),
         "daily":",".join(DAY_VARS),
         "timezone":"Asia/Shanghai", "forecast_days":7}
    url = f"https://api.open-meteo.com/v1/{ep}?" + urllib.parse.urlencode(p)
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Codex/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return None

def safe_get(d, *keys):
    for k in keys:
        try:
            d = d[k]
        except (KeyError, IndexError, TypeError):
            return None
    return d

def weighted_avg(pairs):
    if not pairs: return None
    return sum(w*v for w,v in pairs) / sum(w for w,_ in pairs)

def voted_weather(pairs):
    if not pairs: return "未知"
    counts = {}
    for w, code in pairs:
        if code in (0,1,2,3):
            key = 0
        elif code in (45,48):
            key = 1
        elif code in (51,53,55,56,57,61,63,65,66,67,80,81,82):
            key = 2
        elif code in (71,73,75,77,85,86):
            key = 3
        elif code >= 95:
            key = 4
        else:
            key = 5
        counts[key] = counts.get(key, 0) + w
    labels = {0:"☀ 晴",1:"🌫 雾",2:"🌧 雨",3:"❄ 雪",4:"⛈ 雷暴",5:"🌤 多云"}
    return labels[max(counts, key=counts.get)]

def fmt(v, dec=1):
    if v is None: return "  N/A"
    return f"{v:>{4+dec}.{dec}f}"

def main():
    now = datetime.now(CST)
    today_prefix = now.strftime("%Y-%m-%d")

    print("="*62)
    print("  诸暨市 多模型集合平均预报")
    print(f"  坐标: {LAT}N, {LON}E  |  模型: {' + '.join(m[0] for m in MODELS)}")
    print(f"  来源: Open-Meteo.com  |  {now.strftime('%Y-%m-%d %H:%M')}")
    print("="*62)

    # Fetch all models
    raw = {}
    for name, ep, _ in MODELS:
        print(f"  Fetching {name} ...")
        data = fetch_model(ep)
        if data:
            raw[name] = data
        else:
            print(f"  ✗ {name} 失败")

    if not raw:
        print("\n  ❌ 所有模型失败"); sys.exit(1)

    dates = safe_get(raw[list(raw.keys())[0]], "daily", "time") or []
    if not dates: print("  ❌ 无数据"); sys.exit(1)

    # ── Today Hourly ──
    print(f"\n  ── 今日白天逐时 (体感+湿度) ──")
    print(f"  {'时段':>5s}  {'气温':>5s}  {'体感':>5s}  {'湿度':>5s}  {'天气':>10s}  {'降水':>5s}")
    print("  " + "─"*44)

    for hr in range(6, 18):
        t_pairs, a_pairs, h_pairs, w_pairs, p_pairs = [], [], [], [], []
        for name, _, wt in MODELS:
            if name not in raw: continue
            ts = safe_get(raw[name], "hourly", "time", hr)
            if not ts or not ts.startswith(today_prefix): continue
            v = safe_get(raw[name], "hourly", "temperature_2m", hr)
            if v is not None: t_pairs.append((wt, v))
            v = safe_get(raw[name], "hourly", "apparent_temperature", hr)
            if v is not None: a_pairs.append((wt, v))
            v = safe_get(raw[name], "hourly", "relative_humidity_2m", hr)
            if v is not None: h_pairs.append((wt, v))
            v = safe_get(raw[name], "hourly", "weather_code", hr)
            if v is not None: w_pairs.append((wt, int(v)))
            v = safe_get(raw[name], "hourly", "precipitation", hr)
            if v is not None: p_pairs.append((wt, v))

        if not t_pairs: continue
        t = weighted_avg(t_pairs)
        a = weighted_avg(a_pairs)
        hu = weighted_avg(h_pairs)
        wl = voted_weather(w_pairs)
        p = weighted_avg(p_pairs)
        hu_str = f"{hu:.0f}%" if hu is not None else " N/A"
        print(f"  {hr:02d}:00  {fmt(t)}  {fmt(a)}  {hu_str:>5s}  {'  '+wl:>10s}  {fmt(p):>5s}")

    # ── 7-Day Daily ──
    print(f"\n  ── 未来 7 天预报 ──")
    print(f"  {'日期':>5s}  {'最高温':>5s}  {'最低温':>5s}  {'降水':>6s}  {'风速':>5s}  {'天气':>10s}")
    print("  " + "─"*46)

    month_day = now.strftime("%m-%d")

    for di, date_str in enumerate(dates):
        sd = date_str[-5:]
        if sd == month_day: continue

        tx_p, tn_p, pr_p, wd_p, wc_p = [], [], [], [], []
        for name, _, wt in MODELS:
            if name not in raw: continue
            v = safe_get(raw[name], "daily", "temperature_2m_max", di)
            if v is not None: tx_p.append((wt, v))
            v = safe_get(raw[name], "daily", "temperature_2m_min", di)
            if v is not None: tn_p.append((wt, v))
            v = safe_get(raw[name], "daily", "precipitation_sum", di)
            if v is not None: pr_p.append((wt, v))
            v = safe_get(raw[name], "daily", "wind_speed_10m_max", di)
            if v is not None: wd_p.append((wt, v))
            v = safe_get(raw[name], "daily", "weather_code", di)
            if v is not None: wc_p.append((wt, int(v)))

        wl = voted_weather(wc_p)
        print(f"  {sd:>5s}  {fmt(weighted_avg(tx_p)):>5s}  {fmt(weighted_avg(tn_p)):>5s}  {fmt(weighted_avg(pr_p)):>6s}  {fmt(weighted_avg(wd_p)):>5s}  {'  '+wl:>10s}")

    print("  " + "─"*46)
    print(f"  可用模型: {len(raw)}/{len(MODELS)}")

    # ── Rain Alert ──
    max_r, max_d = 0, ""
    for di, date_str in enumerate(dates):
        for name, _, _ in MODELS:
            if name not in raw: continue
            v = safe_get(raw[name], "daily", "precipitation_sum", di)
            if v and v > max_r:
                max_r, max_d = v, date_str[-5:]
    if max_d:
        icon = "⚠" if max_r >= 10 else "🌦" if max_r >= 2 else "☀"
        print(f"\n  {icon}  {max_d} 降雨最多 ({max_r:.0f}mm)")
    print()

if __name__ == "__main__":
    main()
