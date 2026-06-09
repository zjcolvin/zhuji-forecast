import os
import datetime
import requests

# ==================== 配置 ====================
GRIBSTREAM_TOKEN = os.environ["GRIBSTREAM_TOKEN"]
METEOBLUE_KEY = os.environ["METEOBLUE_KEY"]
DISCORD_WEBHOOK_URL = os.environ["ZBJ_DISCORD_WEBHOOK"]
ZHUJI_LAT, ZHUJI_LON = 29.715, 120.242
# =============================================

CST = datetime.timezone(datetime.timedelta(hours=8))

WEATHER_ICONS = {
    # meteoblue daily pictocode → emoji (官方定义)
    1: "☀️", 2: "🌤️", 3: "⛅", 4: "☁️", 5: "☁️",   # 阴/多云（非雾）
    # 6-7: 阴天有雨/阵雨
    6: "🌧️", 7: "🌦️",
    # 8: 阵雨+雷暴可能
    8: "⛈️",
    # 9-10: 阴天有雪/雪阵雨
    9: "🌧️", 10: "🌧️",   # 大雨/暴雨
    # 11: 多云雨雪混合
    11: "🌧️",
    # 12: 阴天偶有阵雨
    12: "🌦️",
    # 13: 阴天偶有雪
    13: "🌦️",   # 阵雨
    # 14-15: 多云有雨/有雪
    14: "🌧️", 15: "🌨️",
    # 16: 多云间有阵雨
    16: "🌦️",
    # 17: 多云间有阵雪
    17: "🌨️",
    # 18-19: 未使用
    18: "🌦️", 19: "🌤️",   # 有雨云/晴间多云
    # 20: 多云
    20: "☁️",
    # 21-25: 雷暴相关
    21: "🌤️", 22: "⛅",  23: "⛈️", 24: "⛈️", 25: "⛈️",
    # 26-46: 小时级 pictocode_detailed，兜底映射
    26: "🌫️", 27: "🌧️", 28: "🌦️", 29: "⛈️",
    30: "🌨️", 31: "🌨️", 32: "🌧️", 33: "🌦️",
    34: "⛈️", 35: "⛈️", 36: "🌧️", 37: "🌦️",
    38: "🌧️", 39: "🌨️", 40: "🌨️", 41: "🌧️",
    42: "☁️", 43: "🌫️", 44: "🌫️", 45: "🌧️", 46: "🌧️",
}


def pictocode_to_icon(code, temp=None, precip=None, pop=None):
    """基于 pictocode 查表选图标，温度仅用于雪/雨歧义校正"""
    if isinstance(code, (int, float)):
        code = int(code)
    else:
        try:
            code = int(code)
        except (ValueError, TypeError):
            return "🌡️"

    icon = WEATHER_ICONS.get(code, "🌡️")

    # 高温时把雪图标替换为雨图标（>10°C 不会下雪）
    if icon == "🌨️" and temp is not None:
        try:
            if float(temp) > 10:
                icon = "🌧️"
        except (ValueError, TypeError):
            pass

    # 降水概率极高且有雷暴代码时，强化为 ⛈️
    if code in (8, 21, 22, 23, 24, 25) and pop is not None:
        try:
            if float(pop) > 60:
                return "⛈️"
        except (ValueError, TypeError):
            pass

    return icon

WIND_DIRS_16 = [
    "北", "北北东", "东北", "东东北", "东", "东东南", "东南", "南东南",
    "南", "南西南", "西南", "西西南", "西", "西西北", "西北", "北西北",
]


def deg_to_wind_dir(deg):
    if deg is None or deg == "—":
        return "—"
    try:
        idx = round(float(deg) / 22.5) % 16
        return WIND_DIRS_16[idx]
    except (ValueError, TypeError):
        return "—"


def ms_to_kmh(v):
    if v is None or v == "—":
        return "—"
    try:
        return f"{float(v) * 3.6:.0f}"
    except (ValueError, TypeError):
        return "—"


# ---------- 数据获取 ----------

def fetch_meteoblue():
    url = "https://my.meteoblue.com/packages/basic-1h_basic-day"
    params = {"apikey": METEOBLUE_KEY, "lat": ZHUJI_LAT, "lon": ZHUJI_LON, "format": "json"}
    try:
        res = requests.get(url, params=params, timeout=15)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"❌ meteoblue 请求失败: {e}")
        return {}


def fetch_gribstream():
    now = datetime.datetime.now(datetime.timezone.utc)
    ft = now.strftime("%Y-%m-%dT%H:00:00Z")
    ut = (now + datetime.timedelta(hours=6)).strftime("%Y-%m-%dT%H:00:00Z")
    url = "https://gribstream.com/api/v2/gfs/timeseries"
    payload = {
        "fromTime": ft, "untilTime": ut,
        "coordinates": [{"lat": ZHUJI_LAT, "lon": ZHUJI_LON, "name": "zhuji"}],
        "variables": [
            {"name": "TMP", "level": "2 m above ground", "info": "", "alias": "temp_2m"},
            {"name": "APCP", "level": "surface", "info": "", "alias": "precip_surface"},
        ],
    }
    headers = {
        "Authorization": f"Bearer {GRIBSTREAM_TOKEN}",
        "Accept": "application/json",
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        res.raise_for_status()
        raw = res.json()
        # API 返回扁平 list of dicts, 转换为内部兼容的嵌套结构
        # 每条记录: {"forecasted_time": ..., "name": "zhuji", "temp_2m": K, "precip_surface": mm}
        if not isinstance(raw, list):
            print(f"❌ GribStream 返回非列表结构: {type(raw)}")
            return {}
        # 按坐标名分组
        coords = {}
        for row in raw:
            name = row.get("name", "zhuji")
            coords.setdefault(name, []).append(row)
        # 转换为嵌套格式
        results = []
        for name, rows in coords.items():
            variables = {}
            for row in rows:
                ft = row.get("forecasted_time", "")
                for key in row:
                    if key in ("forecasted_time", "lat", "lon", "member", "name", "forecasted_at"):
                        continue
                    alias = key
                    variables.setdefault(alias, []).append({
                        "time": ft,
                        "value": row[key],
                    })
            # 包装为兼容格式
            vars_list = []
            for alias, vals in variables.items():
                vars_list.append({"alias": alias, "values": [v["value"] for v in vals], "times": [v["time"] for v in vals]})
            results.append({"name": name, "variables": vars_list})
        return {"results": results}
    except Exception as e:
        print(f"❌ GribStream 请求失败: {e}")
        return {}


# ---------- 报告生成 ----------

def current_from_hourly(h1, now=None):
    """从每小时数据中取最接近当前时间的条目作为实况
    优先取当前小时（diff=0），其次取下一小时（diff=1 且 > now），避免用历史数据"""
    if not h1:
        return None
    if now is None:
        now = datetime.datetime.now(CST)
    times = h1.get("time", [])
    if not times:
        return None

    best_idx = None
    min_diff = float("inf")
    best_time_str = ""
    for i, t in enumerate(times):
        try:
            dt_utc = datetime.datetime.strptime(str(t), "%Y-%m-%d %H:%M")
            dt_cst = dt_utc.replace(tzinfo=datetime.timezone.utc).astimezone(CST)
            # 同日优先，跨日大幅惩罚
            if dt_cst.date() == now.date():
                diff = abs(dt_cst.hour - now.hour)
            else:
                diff = abs(dt_cst.hour - now.hour) + 24
            if diff < min_diff:
                min_diff = diff
                best_idx = i
                best_time_str = dt_cst.strftime("%Y-%m-%d %H")
        except (ValueError, IndexError):
            continue

    if best_idx is None:
        return None

    def g(key, default=None):
        vals = h1.get(key, [])
        return vals[best_idx] if vals and best_idx < len(vals) else default

    return {
        "temp": g("temperature"),
        "felt": g("felttemperature"),
        "pop": g("precipitation_probability"),
        "precip": g("precipitation"),
        "wind_spd": g("windspeed"),
        "wind_dir": g("winddirection"),
        "pressure": g("sealevelpressure"),
        "humidity": g("relativehumidity"),
        "obs_time": best_time_str,
    }



def _avg_at_indices(lst, idxs):
    if not idxs:
        return None
    valid = [lst[i] for i in idxs if i < len(lst)]
    return round(sum(valid) / len(valid), 1) if valid else None


def _max_at_indices(lst, idxs):
    if not idxs:
        return 0
    valid = [lst[i] for i in idxs if i < len(lst)]
    return int(max(valid)) if valid else 0


def build_detail_today_tomorrow(h1):
    """当天和第二天按 3 小时间隔展示"""
    times = h1.get("time", [])
    temps = h1.get("temperature", [])
    pops = h1.get("precipitation_probability", [])
    felts = h1.get("felttemperature", [])
    icons = h1.get("pictocode", [])
    precips = h1.get("precipitation", [])

    if not times:
        return ""

    # 将 meteoblue UTC 时间转为 CST（北京时间）
    cst_dts = []
    for t in times:
        try:
            dt = datetime.datetime.strptime(str(t), "%Y-%m-%d %H:%M")
            cst_dts.append(dt.replace(tzinfo=datetime.timezone.utc).astimezone(CST))
        except (ValueError, TypeError):
            cst_dts.append(None)
    cst_dates = sorted(set(dt.strftime("%Y-%m-%d") for dt in cst_dts if dt is not None))
    now = datetime.datetime.now(CST)
    now_date = now.strftime("%Y-%m-%d")
    now_hour = now.hour
    # 按当前 CST 日期在数据中定位今天/明天
    if now_date in cst_dates:
        today_str = now_date
        today_idx = cst_dates.index(now_date)
        tomorrow_str = cst_dates[today_idx + 1] if today_idx + 1 < len(cst_dates) else ""
    else:
        today_str = ""
        tomorrow_str = cst_dates[0] if cst_dates else ""

    # 3h slots: 00-03, 03-06, 06-09, 09-12, 12-15, 15-18, 18-21, 21-24
    slot_labels = ["00-03时", "03-06时", "06-09时", "09-12时",
                   "12-15时", "15-18时", "18-21时", "21-24时"]
    slot_ranges = [(0, 3), (3, 6), (6, 9), (9, 12),
                   (12, 15), (15, 18), (18, 21), (21, 24)]

    sections = []
    dates_to_show = []
    if today_str and today_str == now_date:
        dates_to_show.append(("今天", today_str, now_hour))
    if tomorrow_str:
        dates_to_show.append(("明天", tomorrow_str, 0))

    for day_label, date_str, skip_before in dates_to_show:
        lines = []
        for (s, e), label in zip(slot_ranges, slot_labels):
            if skip_before > 0 and s < skip_before:
                continue  # 该时段已开始，不展示
            idxs = []
            for i, dt in enumerate(cst_dts):
                if dt is None:
                    continue
                d = dt.strftime("%Y-%m-%d")
                hr = dt.hour
                if d == date_str and s <= hr < e:
                    idxs.append(i)

            if not idxs:
                continue

            avg_t = _avg_at_indices(temps, idxs)
            avg_f = _avg_at_indices(felts, idxs)
            max_p = _max_at_indices(pops, idxs)
            avg_precip = _avg_at_indices(precips, idxs)
            mid_idx = idxs[len(idxs) // 2]
            icon_id = icons[mid_idx] if icons and mid_idx < len(icons) else 0
            icon = pictocode_to_icon(icon_id, avg_t, avg_precip, max_p)

            # 降水标记
            precip_tag = ""
            if max_p >= 60:
                precip_tag = " 🔴🔴🔴"
            elif max_p >= 40:
                precip_tag = " 🟡🟡"
            elif max_p >= 20:
                precip_tag = " 🟢"

            precip_detail = f" | 💧{max_p}%"
            if avg_precip is not None and avg_precip > 0:
                precip_detail += f" ({avg_precip}mm)"

            felt_str = f" 体感{avg_f}°C" if avg_f is not None else ""
            lines.append(f"  `{label}` {icon} {avg_t}°C{felt_str}{precip_detail}{precip_tag}")

        if lines:
            sections.append(f"**{day_label} ({date_str})**\n" + "\n".join(lines))

    return "\n\n".join(sections)


def build_daily_forecast(dd):
    """未来 7 日预报 —— 列式数据转行，含星期和降水时段标记"""
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    times = dd.get("time", [])
    if not times:
        return ""

    # 获取降水小时分布字符串 (rainspot: 36 chars, 每字符代表 2/3 小时)
    rainspots = dd.get("rainspot", [])

    count = len(times)
    lines = []
    for i in range(min(count, 7)):
        def v(key, default="—"):
            vals = dd.get(key, [])
            return vals[i] if vals and i < len(vals) else default

        date_str = str(v("time")).split(" ")[0]
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            weekday = weekdays[dt.weekday()]
        except ValueError:
            weekday = ""
        tmin = round(float(v("temperature_min", 0)), 1)
        tmax = round(float(v("temperature_max", 0)), 1)
        pop = int(v("precipitation_probability", 0))
        precip = round(float(v("precipitation", 0)), 1)
        icon = pictocode_to_icon(v("pictocode", 0), (tmin + tmax) / 2, precip, pop)

        # 组装
        label = f"**{date_str}** {weekday}" if weekday else f"`{date_str}`"
        line = f"  • {label} {icon} {tmin}~{tmax}°C | 💧{pop}% ({precip}mm)"
        lines.append(line)

    return "\n".join(lines)


def parse_rainspot(rainspot):
    """解析 meteoblue rainspot 字符串，返回降水时段描述
    rainspot: 36个字符，每个字符代表一天中的 2/3 小时 (即每 20 分钟一位)
    0=无降水, 1=有降水
    """
    if not rainspot or not isinstance(rainspot, str) or len(rainspot) < 36:
        return ""

    precip_slots = []
    for idx, ch in enumerate(rainspot[:36]):
        if ch == "1":
            hour = (idx * 2) / 3  # 每个 slot 是 2/3 小时
            precip_slots.append(hour)

    if not precip_slots:
        return ""

    # 合并为时段
    ranges = []
    start = precip_slots[0]
    prev = precip_slots[0]
    for h in precip_slots[1:]:
        if h - prev <= 1:  # 连续（允许 1 小时 gap）
            prev = h
        else:
            ranges.append((start, prev))
            start = h
            prev = h
    ranges.append((start, prev))

    parts = []
    for s, e in ranges:
        sh, sm = int(s), int((s % 1) * 60)
        eh, em = int(e) + 1, int((e % 1) * 60)
        s_str = f"{sh:02d}"
        e_str = f"{eh:02d}"
        if s_str == e_str:
            parts.append(f"{s_str}时")
        else:
            parts.append(f"{s_str}-{e_str}时")

    return "、".join(parts)


def gribstream_highlights(grib_data):
    results = grib_data.get("results", [])
    hints = []
    for coord in results:
        if coord.get("name") != "zhuji":
            continue
        for var in coord.get("variables", []):
            if var.get("alias") == "precip_surface":
                vals = [v for v in var.get("values", []) if v is not None]
                if vals:
                    mx = max(vals)
                    if mx > 10:
                        hints.append(f"⚠️ GribStream 提示未来 6h 累计降水 {mx:.1f}mm，注意短时强对流")
                    elif mx > 5:
                        hints.append(f"🌧️ GribStream 提示未来 6h 有 {mx:.1f}mm 降水")
    return "\n".join(hints)


def generate_report(mb, grib):
    now_cst = datetime.datetime.now(CST).strftime("%Y-%m-%d %H:%M")

    # meteoblue 列式结构
    h1 = mb.get("data_1h", {})
    dd = mb.get("data_day", {})

    # 当前实况
    cur = current_from_hourly(h1)
    if cur:
        current = f"""  🌡️ 气温 **{cur['temp']}°C** (体感 {cur['felt']}°C)
  🌧️ 降水概率 **{cur['pop']}%** ({cur['precip']}mm)
  🍃 风向风速 {deg_to_wind_dir(cur['wind_dir'])} {ms_to_kmh(cur['wind_spd'])} km/h
  🌐 气压 {cur['pressure']} hPa | 💧 湿度 {cur['humidity']}%
  ⏰ 观测时间：{cur['obs_time']} (meteoblue 格点，非站点实测)"""
    else:
        current = "  暂无实时数据"

    # 当天 & 第二天 3h 详情
    detail_lines = build_detail_today_tomorrow(h1)

    # GribStream
    grib_lines = gribstream_highlights(grib)

    # 7 日预报
    daily_lines = build_daily_forecast(dd)

    # 季节性提示
    month = datetime.datetime.now(CST).month
    seasonal = ""
    if 6 <= month <= 7:
        seasonal = "\n> 💡 当前处于梅雨季，注意防潮防雨。"
    elif month in (7, 8, 9):
        seasonal = "\n> 🌀 台风季活跃，关注最新台风动向。"

    parts = [
        f"""---
## 🗺️ 诸暨市动态天气预报 (Zhuji Weather)
> **数据实时更新** | {now_cst} (北京时间) | 数据源：meteoblue × GribStream
---

### 🔴 当前实况
{current}""",
    ]
    if detail_lines:
        parts.append(f"\n### 📊 今天 & 明天 · 逐3小时预报\n{detail_lines}")
    if grib_lines:
        parts.append(f"\n### ⚡ 短时预警\n{grib_lines}")
    if daily_lines:
        parts.append(f"\n### 📅 未来七日展望\n{daily_lines}")
    parts.append(seasonal)

    return "\n".join(parts)


# ---------- Discord 推送 ----------

def send_to_discord(content):
    if not content:
        print("❌ 内容为空")
        return False
    payload = {
        "content": content,
        "username": "诸暨天气助手 🌤️",
        "avatar_url": "https://emoji.discord.st/v1/natural/27281.png",
    }
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
        print("📤 Discord 推送成功！")
        return True
    except Exception as e:
        print(f"❌ Discord 推送失败: {e}")
        return False


# ---------- 主流程 ----------

def main():
    print("=" * 50)
    print("  诸暨市天气预报 · Discord 推送器")
    print("=" * 50)

    print("🛰️ 正在获取气象数据...")
    mb = fetch_meteoblue()
    grib = fetch_gribstream()

    if not mb and not grib:
        print("⚠️ 所有数据源失败")
        return

    print("📝 正在生成预报卡片...")
    report = generate_report(mb, grib)

    if report:
        print("\n--- 预览 ---")
        print(report)
        print("---  end  ---\n")
        send_to_discord(report)


if __name__ == "__main__":
    main()
