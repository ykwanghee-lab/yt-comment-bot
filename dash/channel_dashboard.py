# -*- coding: utf-8 -*-

"""유튜브 멀티채널 현황 대시보드 (2026-10-17)



- channels.json 의 채널 토큰으로 각 채널의 구독자·조회수·영상 수·최근 업로드 성과를 한 번에 모은다.

- 매일 스냅샷(채널통계_기록.json)을 남겨 1일·7일·30일 증감을 계산한다(애널리틱스 API 권한 없이도 가능).

- 댓글봇 검토 대기 건수(검토필요_<채널>.html)와 마지막 실행 시각(run_log.txt)도 같이 보여 준다.

- 폴더 구조: D:/0000_프로그램들/유튜브채널대시보드(이 프로그램) / D:/0000_프로그램들/유튜브댓글자동봇(토큰·채널 설정 — BOT_DIR). 댓글봇 폴더를 옮기면 BOT_DIR 또는 환경변수 YT_BOT_DIR 를 바꾼다.

- 산출물: 채널대시보드.html (이 폴더) → 구글 드라이브 폴더 → GitHub Pages(댓글봇 _pages/channels.html) 푸시 → 폰에서 링크로 열람.

- 실행: 채널대시보드_실행.bat (수동) / setup_schedule_dashboard.bat (1시간마다 자동)

"""

import html

import io

import json

import os

import re

import shutil

import subprocess

import sys

from datetime import datetime, timedelta, timezone



try:

    from google.oauth2.credentials import Credentials

    from googleapiclient.discovery import build

except ImportError:

    print("필요한 라이브러리가 없습니다. 먼저: pip install -r requirements.txt")

    sys.exit(1)



BASE_DIR = os.path.dirname(os.path.abspath(__file__))          # 이 프로그램 폴더(산출물·기록 저장)

# 댓글봇 폴더(채널 토큰·channels.json·config.json·검토필요 html·run_log·_pages 를 여기서 읽는다)

BOT_DIR = os.environ.get("YT_BOT_DIR") or r"D:\0000_프로그램들\유튜브댓글자동봇"

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

OUT_NAME = "채널대시보드.html"

HIST_PATH = os.environ.get("YT_DASH_HIST") or os.path.join(BASE_DIR, "채널통계_기록.json")

# 클라우드(GitHub Actions): channels.html 을 이 경로에 쓰고 git 푸시는 워크플로가 한다
PAGES_OUT = os.environ.get("YT_DASH_PAGES_OUT", "")

RECENT_N = 8          # 채널당 최근 영상 수

SHORT_SEC = 180       # 이 길이 이하면 쇼츠로 분류

KST = timezone(timedelta(hours=9))





def load_json(path, default):

    try:

        return json.load(io.open(path, encoding="utf-8"))

    except Exception:

        return default





def iso_dur_to_sec(s):

    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")

    if not m:

        return 0

    h, mi, se = (int(x) if x else 0 for x in m.groups())

    return h * 3600 + mi * 60 + se





def fmt_int(n):

    try:

        return f"{int(n):,}"

    except Exception:

        return "-"





def fmt_k(n):
    """구독자·조회수 표기: 끝자리까지 전부(천 단위 쉼표). 2026-10-18 사용자 요청으로 (천)/(백만) 축약 해제."""
    return fmt_int(n)


def fmt_delta(n):

    if n is None:

        return '<span class="na">-</span>'

    n = int(n)

    if n > 0:

        return f'<span class="up">+{n:,}</span>'

    if n < 0:

        return f'<span class="down">{n:,}</span>'

    return '<span class="flat">0</span>'





def ago(dt):

    d = datetime.now(KST) - dt

    if d.days >= 1:

        return f"{d.days}일 전"

    h = d.seconds // 3600

    return f"{h}시간 전" if h else f"{d.seconds // 60}분 전"





def review_count(name):

    p = os.path.join(BOT_DIR, f"검토필요_{name}.html")

    if not os.path.exists(p):

        return None

    m = re.search(r"총 (\d+)건", io.open(p, encoding="utf-8").read())

    return int(m.group(1)) if m else None





def last_bot_run():

    p = os.path.join(BOT_DIR, "run_log.txt")

    if not os.path.exists(p):

        return ""

    lines = [l for l in io.open(p, encoding="utf-8", errors="ignore").read().splitlines() if l.strip()]

    if not lines:

        return ""

    m = re.match(r"\[([^\]]+)\]", lines[-1])

    return m.group(1) if m else ""





def fetch_channel(cfg):

    creds = Credentials.from_authorized_user_file(os.path.join(BOT_DIR, cfg["token"]), SCOPES)

    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    ch = yt.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()["items"][0]

    st = ch["statistics"]

    sn = ch["snippet"]

    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]

    info = {

        "name": cfg["name"],

        "id": ch["id"],

        "title": sn.get("title", cfg["name"]),

        "handle": sn.get("customUrl", ""),

        "thumb": (sn.get("thumbnails", {}).get("default") or {}).get("url", ""),

        "subs": int(st.get("subscriberCount", 0)),

        "views": int(st.get("viewCount", 0)),

        "videos": int(st.get("videoCount", 0)),

        "lang": cfg.get("lang", "ko"),

        "auto_post": cfg.get("auto_post", True),

        "recent": [],

    }

    try:

        items = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=RECENT_N).execute().get("items", [])

        ids = [it["contentDetails"]["videoId"] for it in items]

        if ids:

            vids = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids)).execute().get("items", [])

            for v in vids:

                vs = v["statistics"]

                pub = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00")).astimezone(KST)

                sec = iso_dur_to_sec(v["contentDetails"].get("duration"))

                info["recent"].append({

                    "id": v["id"],

                    "title": v["snippet"].get("title", ""),

                    "published": pub,

                    "views": int(vs.get("viewCount", 0)),

                    "likes": int(vs.get("likeCount", 0)) if "likeCount" in vs else None,

                    "comments": int(vs.get("commentCount", 0)) if "commentCount" in vs else None,

                    "sec": sec,

                    "short": sec <= SHORT_SEC,

                })

            info["recent"].sort(key=lambda x: x["published"], reverse=True)

    except Exception as e:

        info["recent_err"] = str(e)[:120]

    return info





def update_history(channels):

    hist = load_json(HIST_PATH, {})

    today = datetime.now(KST).strftime("%Y-%m-%d")

    hist.setdefault(today, {})

    for c in channels:

        hist[today][c["name"]] = {"subs": c["subs"], "views": c["views"], "videos": c["videos"]}

    # 400일 이상 된 기록은 버림

    cutoff = (datetime.now(KST) - timedelta(days=400)).strftime("%Y-%m-%d")

    hist = {d: v for d, v in hist.items() if d >= cutoff}

    io.open(HIST_PATH, "w", encoding="utf-8").write(json.dumps(hist, ensure_ascii=False, indent=1))

    return hist





def delta(hist, name, key, days, cur):

    """days 일 전(또는 그보다 가까운 가장 오래된 기록)과의 차이. 기록이 없으면 None."""

    target = (datetime.now(KST) - timedelta(days=days)).strftime("%Y-%m-%d")

    dates = sorted(d for d in hist if d <= target and name in hist[d])

    if not dates:

        older = sorted(d for d in hist if name in hist[d])

        if len(older) < 2:

            return None

        dates = [older[0]]  # 기록이 짧으면 가장 오래된 기록 기준

    return cur - hist[dates[-1]][name][key]





def sparkline(hist, name, key, days=30):

    pts = []

    for d in sorted(hist):

        if name in hist[d]:

            pts.append(hist[d][name][key])

    pts = pts[-days:]

    if len(pts) < 2:

        return ""

    lo, hi = min(pts), max(pts)

    w, h = 120, 28

    span = (hi - lo) or 1

    coords = []

    for i, p in enumerate(pts):

        x = i * w / (len(pts) - 1)

        y = h - 2 - (p - lo) * (h - 4) / span

        coords.append(f"{x:.1f},{y:.1f}")

    return f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none"><polyline points="{" ".join(coords)}" /></svg>'





def render(channels, hist, errors):

    now = datetime.now(KST)

    total_subs = sum(c["subs"] for c in channels)

    total_views = sum(c["views"] for c in channels)

    total_videos = sum(c["videos"] for c in channels)

    d1_subs = sum((delta(hist, c["name"], "subs", 1, c["subs"]) or 0) for c in channels)

    d1_views = sum((delta(hist, c["name"], "views", 1, c["views"]) or 0) for c in channels)

    week_ago = now - timedelta(days=7)

    uploads_7d = sum(1 for c in channels for v in c["recent"] if v["published"] >= week_ago)

    review_total = sum((review_count(c["name"]) or 0) for c in channels)

    bot_run = last_bot_run()

    cfg = load_json(os.path.join(BOT_DIR, "config.json"), {})

    comment_url = cfg.get("dashboard_url", "")



    cards = []

    # 정렬: 최근 영상이 공개된 채널이 위(같은 날이면 구독자 많은 채널 위) · 업로드가 없거나 오래된 채널은 아래
    def sort_key(c):
        last = c["recent"][0]["published"] if c["recent"] else None
        day = last.strftime("%Y-%m-%d") if last else "0000-00-00"
        return (day, c["subs"])
    for c in sorted(channels, key=sort_key, reverse=True):

        name = html.escape(c["title"])

        handle = html.escape(c["handle"])

        rc = review_count(c["name"])

        last = c["recent"][0]["published"] if c["recent"] else None

        up7 = sum(1 for v in c["recent"] if v["published"] >= week_ago)

        views7 = sum(v["views"] for v in c["recent"] if v["published"] >= week_ago)

        mode = "자동답글" if c["auto_post"] else "검토만"

        lang = "EN" if c["lang"] == "en" else "KO"

        rows = []

        for v in c["recent"][:RECENT_N]:

            t = html.escape(v["title"])

            if len(v["title"]) > 42:

                t = html.escape(v["title"][:42]) + "…"

            kind = '<span class="tag short">쇼츠</span>' if v["short"] else '<span class="tag long">롱폼</span>'

            rows.append(

                f'<li><a href="https://www.youtube.com/watch?v={v["id"]}" target="_blank" rel="noopener">{t}</a>'

                f'<div class="vmeta">{kind} {v["published"].strftime("%m-%d")} · 조회 <b>{fmt_k(v["views"])}</b>'

                f' · 좋아요 {fmt_int(v["likes"]) if v["likes"] is not None else "-"} · 댓글 {fmt_int(v["comments"]) if v["comments"] is not None else "-"}</div></li>'

            )

        recent_html = "<ul class='vlist'>" + "".join(rows) + "</ul>" if rows else '<div class="empty">업로드된 영상이 없습니다.</div>'

        err = f'<div class="err">최근 영상 조회 실패: {html.escape(c.get("recent_err",""))}</div>' if c.get("recent_err") else ""

        if last is None:
            warn = ' · <span class="warn">⚠영상없음</span>'
        elif (now - last).days >= 30:
            warn = ' · <span class="warn">⚠관리안됨</span>'
        elif (now - last).days >= 7:
            warn = ' · <span class="warn">⚠업로드공백</span>'
        else:
            warn = ""

        d1s = delta(hist, c["name"], "subs", 1, c["subs"])
        cards.append(f"""
<details class="card">
  <summary class="row">
    <img src="{html.escape(c["thumb"])}" alt="" class="avatar">
    <div class="rowmain"><div class="rname">{name}</div><div class="rsub">업로드 {(ago(last) if last else "없음")} · 검토 <b class="{'hot' if rc else ''}">{rc if rc is not None else '-'}</b>{warn}</div></div>
    <div class="rnum"><div class="rv"><span class="rl">구독</span>{fmt_k(c["subs"])}</div><div class="rv"><span class="rl">조회</span>{fmt_k(c["views"])}</div></div>
  </summary>
  <div class="body">
  <div class="handle"><a href="https://www.youtube.com/channel/{c["id"]}" target="_blank" rel="noopener">{handle} 채널 열기 →</a> · {lang} · {mode} {sparkline(hist, c["name"], "subs")}</div>
  <div class="stats">
    <div class="stat"><div class="k">구독자</div><div class="v">{fmt_k(c["subs"])}</div><div class="d">1일 {fmt_delta(d1s)}<br>7일 {fmt_delta(delta(hist, c["name"], "subs", 7, c["subs"]))}<br>30일 {fmt_delta(delta(hist, c["name"], "subs", 30, c["subs"]))}</div></div>
    <div class="stat"><div class="k">총 조회수</div><div class="v">{fmt_k(c["views"])}</div><div class="d">1일 {fmt_delta(delta(hist, c["name"], "views", 1, c["views"]))}<br>7일 {fmt_delta(delta(hist, c["name"], "views", 7, c["views"]))}<br>30일 {fmt_delta(delta(hist, c["name"], "views", 30, c["views"]))}</div></div>
    <div class="stat"><div class="k">영상 수</div><div class="v">{fmt_int(c["videos"])}</div><div class="d">최근 7일 업로드 {up7}개<br>그 조회 {fmt_k(views7)}</div></div>
    <div class="stat"><div class="k">마지막 업로드</div><div class="v small">{(ago(last) if last else "-")}{warn}</div><div class="d">댓글 검토 대기 <b class="{'hot' if rc else ''}">{rc if rc is not None else '-'}</b>건</div></div>
  </div>
  <div class="vhead">최근 영상 {len(c["recent"])}개</div>{recent_html}{err}
  </div>
</details>""")



    err_html = ""

    if errors:

        err_html = '<div class="errbox">' + "<br>".join(html.escape(e) for e in errors) + "</div>"



    return f"""<!DOCTYPE html>

<html lang="ko"><head><meta charset="utf-8">

<meta name="viewport" content="width=device-width, initial-scale=1">

<meta http-equiv="refresh" content="1800">

<title>유튜브 채널 대시보드</title>

<style>
  :root{{--fs:17px;--num:28px;--sub:14px;--title:21px}}
  html.big{{--fs:20px;--num:34px;--sub:17px;--title:24px}}
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;background:#0b0d12;color:#f3f4f6;margin:0 auto;padding:14px 14px 40px;max-width:900px;font-size:var(--fs);line-height:1.5}}
  header{{position:sticky;top:0;background:#0b0d12;padding:6px 0 8px;z-index:5;display:flex;align-items:center;gap:10px}}
  header .hd{{flex:1;min-width:0}}
  h1{{font-size:var(--title);margin:0 0 2px;color:#fff;white-space:nowrap}}
  .sub{{font-size:var(--sub);color:#c3c8d1}}
  .sub a{{color:#9ec5ff;text-decoration:underline}}
  .btn{{flex:none;background:#263042;color:#fff;border:1px solid #3b4a63;border-radius:12px;padding:8px 12px;font-size:var(--sub);font-weight:700;cursor:pointer;min-height:40px}}
  .totals{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:8px 0 8px}}
  .tot{{background:#1b2029;border-radius:14px;padding:8px 12px}}
  .tot .k{{font-size:var(--sub);color:#c3c8d1}} .tot .v{{font-size:calc(var(--num) - 4px);font-weight:800;margin-top:0;color:#fff;letter-spacing:-0.5px;line-height:1.2}} .tot .d{{font-size:var(--sub);color:#c3c8d1;margin-top:2px}}
  .line{{font-size:var(--sub);color:#c3c8d1;margin:0 0 10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}} .line b{{color:#fff}}
  .card{{background:#151922;border:1px solid #2b3240;border-radius:14px;padding:0;margin:0 0 8px}}
  .card:nth-of-type(odd){{background:#242a36;border-color:#3a4356}}   /* 홀수 번째 채널 = 연한 회색(줄 구분) */
  .card:nth-of-type(odd) .stat{{background:#2c3342}}
  .card summary{{list-style:none}} .card summary::-webkit-details-marker{{display:none}}
  .row{{display:flex;align-items:center;gap:10px;padding:7px 12px;cursor:pointer}}
  .rowmain{{flex:1;min-width:0}} .rname{{font-size:var(--fs);font-weight:800;color:#fff;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .rsub{{font-size:var(--sub);color:#c3c8d1;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .rnum{{text-align:right;flex:none;max-width:44%}} .rv{{font-size:calc(var(--fs) + 1px);font-weight:800;color:#fff;letter-spacing:-0.3px;line-height:1.3;white-space:nowrap}} .rl{{font-size:calc(var(--sub) - 2px);font-weight:600;color:#c3c8d1;margin-right:5px}}
  .card[open] .row{{border-bottom:1px solid #2b3240}}
  .body{{padding:12px 14px 14px}}
  .vhead{{font-size:var(--fs);color:#9ec5ff;font-weight:700;margin-top:10px}}
  .chhead{{display:flex;align-items:center;gap:12px}}
  .avatar{{width:40px;height:40px;border-radius:50%;background:#262a33;flex:none}}
  .chname{{flex:1;min-width:0}} .chname a{{color:#fff;font-weight:800;font-size:var(--title);text-decoration:none;line-height:1.25}}
  .handle{{font-size:var(--sub);color:#c3c8d1;display:flex;align-items:center;gap:8px;flex-wrap:wrap}} .handle a{{color:#9ec5ff}}
  .spark{{width:110px;height:34px;flex:none}} .spark polyline{{fill:none;stroke:#9ec5ff;stroke-width:2.2}}
  .stats{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0 6px}}
  .stat{{background:#1b2029;border-radius:12px;padding:12px}}
  .stat .k{{font-size:var(--sub);color:#c3c8d1}} .stat .v{{font-size:var(--num);font-weight:800;margin-top:2px;color:#fff;letter-spacing:-0.5px}} .stat .v.small{{font-size:calc(var(--num) - 8px)}}
  .stat .d{{font-size:var(--sub);color:#d5d9e0;margin-top:5px;line-height:1.55}}
  .up{{color:#6ee7a8;font-weight:800}} .down{{color:#ff8a80;font-weight:800}} .flat,.na{{color:#9aa0a6}}
  .hot{{color:#ffd54f}} .warn{{color:#ff8a80;font-size:var(--sub);font-weight:800;display:inline-block;margin-top:2px}}
  details summary{{cursor:pointer;font-size:var(--fs);color:#9ec5ff;margin-top:6px;padding:10px 0;font-weight:700}}
  .vlist{{list-style:none;padding:0;margin:4px 0 0}}
  .vlist li{{padding:12px 0;border-top:1px solid #2b3240;font-size:var(--fs)}}
  .vlist a{{color:#fff;text-decoration:none;font-weight:600}}
  .vmeta{{font-size:var(--sub);color:#d5d9e0;margin-top:5px}}
  .tag{{display:inline-block;font-size:calc(var(--sub) - 2px);padding:2px 8px;border-radius:9px;margin-right:6px;font-weight:700}}
  .tag.short{{background:#4a3566;color:#e9d5ff}} .tag.long{{background:#1f4a39;color:#b9f0d0}}
  .empty,.err,.errbox{{font-size:var(--sub);color:#c3c8d1;padding:8px 0}} .err,.errbox{{color:#ff8a80}}
  footer{{font-size:var(--sub);color:#9aa0a6;text-align:center;padding:16px 0 30px}}
  @media (min-width:600px){{.totals{{grid-template-columns:repeat(4,1fr)}} .stats{{grid-template-columns:repeat(4,1fr)}}}}
</style>
<script>
  (function(){{try{{if(localStorage.getItem("ytdash_big")==="1")document.documentElement.classList.add("big");}}catch(e){{}}}})();
  function toggleBig(){{var h=document.documentElement;h.classList.toggle("big");try{{localStorage.setItem("ytdash_big",h.classList.contains("big")?"1":"0");}}catch(e){{}}}}
</script></head>

<body>

<header>
  <div class="hd">
  <h1>📺 채널 대시보드</h1>
  <div class="sub">갱신 {now.strftime("%m-%d %H:%M")} · {len(channels)}채널{(' · <a href="' + html.escape(comment_url) + '">댓글 검토 →</a>') if comment_url else ''}</div>
  </div>
  <button class="btn" onclick="toggleBig()" type="button">글자 크게</button>
</header>

<div class="totals">
  <div class="tot"><div class="k">총 구독자</div><div class="v">{fmt_k(total_subs)}</div><div class="d">오늘 {fmt_delta(d1_subs)}</div></div>
  <div class="tot"><div class="k">댓글 검토 대기</div><div class="v {'hot' if review_total else ''}">{review_total}</div><div class="d">전 채널 합계</div></div>
</div>
<div class="line">총 조회수 <b>{fmt_k(total_views)}</b> (오늘 {fmt_delta(d1_views)}) · 총 영상 <b>{fmt_int(total_videos)}</b> · 7일 업로드 <b>{uploads_7d}</b>개</div>
{err_html}

{"".join(cards)}

<footer>채널 줄을 누르면 자세히 보입니다. 순서 = 최근 영상 공개일 순(같은 날이면 구독자 순). 증감은 매일 스냅샷 비교값입니다(기록이 쌓이면 7일·30일도 채워집니다). 30분마다 자동 새로고침.</footer>

</body></html>"""





def publish(out_path):

    cfg = load_json(os.path.join(BOT_DIR, "config.json"), {})

    if PAGES_OUT:
        shutil.copy2(out_path, PAGES_OUT)
        print("클라우드: channels.html 저장 →", PAGES_OUT)
        return

    # 1) 구글 드라이브 폴더

    drive = cfg.get("mobile_sync_folder") or ""

    if drive and os.path.isdir(drive):

        try:

            shutil.copy2(out_path, os.path.join(drive, OUT_NAME))

        except Exception as e:

            print("드라이브 복사 실패:", e)

    # 2) GitHub Pages (_pages/channels.html)

    pages = os.path.join(BOT_DIR, "_pages")

    if os.path.isdir(os.path.join(pages, ".git")):

        try:

            shutil.copy2(out_path, os.path.join(pages, "channels.html"))

            subprocess.run(["git", "add", "-A"], cwd=pages, capture_output=True)

            chk = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=pages)

            if chk.returncode != 0:

                subprocess.run(["git", "commit", "-m", "channels " + datetime.now(KST).strftime("%Y-%m-%d_%H-%M")], cwd=pages, capture_output=True)

                r = subprocess.run(["git", "push"], cwd=pages, capture_output=True, text=True)

                print("GitHub Pages 푸시:", "완료" if r.returncode == 0 else ("실패 " + r.stderr[:200]))

            else:

                print("GitHub Pages: 변경 없음")

        except Exception as e:

            print("GitHub Pages 푸시 실패:", e)

        url = (cfg.get("dashboard_url") or "").rstrip("/")

        if url:

            print("폰 링크:", url + "/channels.html")





def main():

    cfgs = load_json(os.path.join(BOT_DIR, "channels.json"), {"channels": []}).get("channels", [])

    channels, errors = [], []

    for c in cfgs:

        if not os.path.exists(os.path.join(BOT_DIR, c.get("token", ""))):

            errors.append(f"{c.get('name')}: 토큰 파일 없음")

            continue

        try:

            channels.append(fetch_channel(c))

            print("OK", c["name"])

        except Exception as e:

            errors.append(f"{c.get('name')}: {str(e)[:120]}")

            print("ERR", c["name"], str(e)[:120])

    hist = update_history(channels)

    out = render(channels, hist, errors)

    out_path = os.path.join(BASE_DIR, OUT_NAME)

    io.open(out_path, "w", encoding="utf-8").write(out)

    print("저장:", out_path)

    publish(out_path)





if __name__ == "__main__":

    main()

