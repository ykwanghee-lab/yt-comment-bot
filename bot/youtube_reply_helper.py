#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
유튜브 댓글 대댓글 도우미 (멀티 채널 · 조건부 자동 게시)
────────────────────────────────────────────────
내 여러 브랜드 채널에 달린 댓글을 각각 가져와서
  1) '단순 감사/칭찬' 댓글  -> 따뜻한 답글을 자동으로 게시
  2) '질문/불만/복잡' 댓글  -> 게시하지 않고 채널별 '검토필요.html' 목록으로 정리
     (각 댓글에 답글 초안 + 유튜브 바로가기 링크 포함 -> 폰/앱에서 직접 답글)

기본은 '미리보기(dry-run)' 모드라 아무것도 게시되지 않습니다.
설정 파일(config.json)에서 auto_post 를 true 로 바꿔야 실제로 답글이 달립니다.

채널 목록은 channels.json 에 저장됩니다. 새 채널은 '채널추가.bat'(add_channel.py)로 추가하세요.
정상 실행(이 파일)은 절대 브라우저를 띄우지 않습니다. 토큰이 없는 채널은 건너뜁니다.
"""

import os
import sys
import re
import json
import html
import random
import shutil
import subprocess
import datetime

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("필요한 라이브러리가 없습니다. 먼저 아래 명령을 실행하세요:")
    print("  pip install -r requirements.txt")
    sys.exit(1)

# 댓글을 읽고 답글을 달기 위해 필요한 권한 범위
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CHANNELS_PATH = os.path.join(BASE_DIR, "channels.json")
CLIENT_SECRET_PATH = os.path.join(BASE_DIR, "client_secret.json")
RUN_LOG_PATH = os.path.join(BASE_DIR, "run_log.txt")
NOTIFY_STATE_PATH = os.path.join(BASE_DIR, "알림보낸검토.json")


def load_notified() -> set:
    if os.path.exists(NOTIFY_STATE_PATH):
        try:
            return set(json.load(open(NOTIFY_STATE_PATH, encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_notified(ids) -> None:
    try:
        json.dump(sorted(ids), open(NOTIFY_STATE_PATH, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception:
        pass


def telegram_send(cfg, text) -> bool:
    """검토 알림을 폰 텔레그램으로 전송."""
    token = (cfg.get("telegram_token") or "").strip()
    chat = (cfg.get("telegram_chat_id") or "").strip()
    if not token or not chat or token.startswith("your_"):
        return False
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": text,
                            "disable_web_page_preview": True}, timeout=10)
        return True
    except Exception as e:
        print(f"[텔레그램 전송 실패] {e}")
        return False


def notify_review(cfg, all_reviews) -> None:
    """검토 큐로 새로 들어온 댓글을 폰 텔레그램으로 링크 알림 (중복 방지).
    이미 답글이 달린 댓글은 all_reviews에 애초에 포함되지 않으므로 자동으로 목록/알림에서 빠진다."""
    if not cfg.get("notify_review", False):
        return
    first = not os.path.exists(NOTIFY_STATE_PATH)
    notified = load_notified()
    new_items = [it for it in all_reviews
                 if it.get("comment_id") and it["comment_id"] not in notified]
    if not new_items:
        return

    url = (cfg.get("dashboard_url") or "").strip()
    link_line = (f"\n\n📊 대시보드 열기 (클릭):\n{url}" if url
                 else "\n\n📊 구글 드라이브 '대시보드.html' 확인")

    if first:
        # 최초 활성화: 기존 백로그는 링크 스팸 대신 요약 1건만 보내고 기준선 저장
        telegram_send(cfg, f"🔔 유튜브 댓글 검토 알림이 켜졌습니다.\n"
                           f"현재 검토 대기 {len(new_items)}건은 아래 대시보드에서 확인하세요."
                           + link_line)
    else:
        chans = sorted(set(it.get("channel", "") for it in new_items))
        # 새 댓글 미리보기 (최대 5건: 채널 · 작성자 · 내용요약)
        preview = []
        for it in new_items[:5]:
            author = it.get("author", "")
            text = (it.get("text", "") or "").replace("\n", " ").strip()
            if len(text) > 30:
                text = text[:30] + "…"
            preview.append(f"• [{it.get('channel','')}] {author}: {text}")
        more = f"\n…외 {len(new_items) - 5}건" if len(new_items) > 5 else ""
        telegram_send(cfg, f"🔔 새로 답글 검토할 댓글 {len(new_items)}건 "
                           f"(채널: {', '.join(chans)})\n\n"
                           + "\n".join(preview) + more
                           + link_line)

    for it in new_items:
        notified.add(it["comment_id"])
    save_notified(notified)


def push_dashboard(cfg) -> None:
    """최신 대시보드를 GitHub Pages로 즉시 푸시 (알림 링크가 항상 최신이 되도록). 실패해도 무시."""
    if not cfg.get("push_pages_after_run", False):
        return
    ps1 = os.path.join(BASE_DIR, "push_pages.ps1")
    if not os.path.exists(ps1):
        return
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", ps1],
            cwd=BASE_DIR, timeout=120,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print("  [Pages] 대시보드 GitHub Pages 푸시 완료")
    except Exception as e:
        print(f"  [Pages 푸시 오류] {e}")


# ─────────────────────────────────────────────
# 설정 / 채널목록 / 로그 불러오기
# ─────────────────────────────────────────────
def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"설정 파일이 없습니다: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # 클라우드(GitHub Actions): 비밀값(텔레그램 토큰 등)은 저장소에 올리지 않고
    # cloud_secrets.py 가 실행 때만 만드는 secret_config.json 에서 덮어쓴다.
    secret_path = os.path.join(BASE_DIR, "secret_config.json")
    if os.path.exists(secret_path):
        try:
            with open(secret_path, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            print(f"[비밀설정 읽기 실패] {e}")
    return cfg


def load_channels():
    """channels.json 에서 관리 채널 목록을 읽는다. 없으면 기존 단일 token.json 로 폴백."""
    if os.path.exists(CHANNELS_PATH):
        with open(CHANNELS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("channels", [])
    # 폴백: 예전 단일 채널 방식
    legacy = os.path.join(BASE_DIR, "token.json")
    if os.path.exists(legacy):
        return [{"name": "내 채널", "token": "token.json"}]
    return []


def safe_name(name):
    """폴더/파일명에 쓸 수 있게 이름을 정리."""
    s = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip()
    return s or "채널"


def done_log_path(ch):
    return os.path.join(BASE_DIR, f"이미처리한댓글_{safe_name(ch['name'])}.json")


def load_done_ids(ch):
    p = done_log_path(ch)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            try:
                return set(json.load(f))
            except Exception:
                return set()
    return set()


def save_done_ids(ch, done_ids):
    with open(done_log_path(ch), "w", encoding="utf-8") as f:
        json.dump(sorted(done_ids), f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# 인증 (정상 실행에서는 브라우저를 절대 띄우지 않음)
# ─────────────────────────────────────────────
def get_service(token_file):
    """토큰 파일로 서비스 생성. 토큰이 없거나 되살릴 수 없으면 None 반환(건너뜀)."""
    token_path = os.path.join(BASE_DIR, token_file)
    if not os.path.exists(token_path):
        return None
    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    except Exception:
        return None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            except Exception:
                return None
        else:
            return None
    return build("youtube", "v3", credentials=creds)


def get_my_channel(youtube):
    resp = youtube.channels().list(part="id,snippet", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        return None, None
    return items[0]["id"], items[0]["snippet"].get("title", "")


# ─────────────────────────────────────────────
# 댓글 가져오기
# ─────────────────────────────────────────────
def fetch_comment_threads(youtube, channel_id, max_count):
    threads = []
    page_token = None
    while len(threads) < max_count:
        resp = youtube.commentThreads().list(
            part="snippet,replies",
            allThreadsRelatedToChannelId=channel_id,
            maxResults=min(100, max_count - len(threads)),
            order="time",
            textFormat="plainText",
            pageToken=page_token,
        ).execute()
        threads.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return threads[:max_count]


def owner_already_replied(thread, channel_id):
    replies = thread.get("replies", {}).get("comments", [])
    for r in replies:
        author_id = r["snippet"].get("authorChannelId", {}).get("value")
        if author_id == channel_id:
            return True
    return False


# ─────────────────────────────────────────────
# 분류 로직
# ─────────────────────────────────────────────
_HANGUL_RE = re.compile(r"[가-힣]")
_CJK_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


_KANA_RE = re.compile(r"[぀-ヿ]")   # 히라가나·가타카나 → 일본어 확정


def comment_lang(text, channel_lang="ko"):
    """댓글 언어 판정: 한글이 하나라도 있으면 ko. 가나(히라가나·가타카나)가 있으면 ja.
    없으면 영어 채널은 en, 한국어·일본어 채널은 라틴 문자만 있을 때(한자 없음) en,
    그 밖엔(한자만 등) 채널 기본 언어."""
    s = text or ""
    if _HANGUL_RE.search(s):
        return "ko"
    if _KANA_RE.search(s):
        return "ja"
    if channel_lang == "en":
        return "en"
    if re.search(r"[A-Za-z]", s) and not _CJK_RE.search(s):
        return "en"
    return channel_lang


def _cfg_lang(cfg, key, lang):
    """config 의 언어별 항목 조회: key_<lang> 이 있으면 그것, 없으면 기본(한국어) key."""
    if lang and lang != "ko":
        v = cfg.get(f"{key}_{lang}")
        if v:
            return v
    return cfg[key]


def classify(text, cfg, lang="ko"):
    t = text.strip()
    low = t.lower()

    cls = _cfg_lang(cfg, "classification", lang)
    review_kw = cls["review_keywords"]
    question_marks = cls["question_marks"]
    auto_kw = cls["auto_reply_keywords"]
    max_len = cls["auto_max_length"]

    if any(q in t for q in question_marks):
        return "review", "질문으로 보임(물음표/의문 표현)"
    for kw in review_kw:
        if kw.lower() in low:
            return "review", f"검토 키워드 '{kw}' 포함"

    # 명확한 감사/칭찬 키워드는 그대로 자동
    for kw in auto_kw:
        if kw.lower() in low:
            return "auto", f"감사/칭찬 키워드 '{kw}' 포함"

    # 너무 긴 댓글(긴 사연/문의 가능성)은 사람이 직접 확인
    if len(t) > max_len:
        return "review", f"댓글이 김({len(t)}자) → 직접 확인"

    # 질문·불만·민감어가 없고 길이도 짧으면: 일반 시청 반응으로 보고 감사 자동답글
    # (막장 사연 채널은 '감사'보다 스토리 반응 댓글이 대부분이라 이걸 자동으로 처리)
    return "auto", "일반 시청 반응(감사 자동답글)"


# 이모지·픽토그램·변형선택자 등 특수기호 제거용 (유튜브 답글 게시 오류 예방)
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # 이모지·픽토그램 전반
    "\U00002600-\U000027BF"   # 기타 기호·딩벳
    "\U00002190-\U000021FF"   # 화살표
    "\U00002B00-\U00002BFF"   # 기타 기호·화살표
    "\U0000FE00-\U0000FE0F"   # 변형 선택자(이모지 표시)
    "\U0001F1E6-\U0001F1FF"   # 국기
    "\U0000200D"              # ZWJ(이모지 결합)
    "\U00002122\U00002139"    # ™ ℹ
    "]+", flags=re.UNICODE)


def strip_specials(text: str) -> str:
    """이모지·특수기호 제거 + 공백 정리 → 순수 텍스트 답글."""
    text = _EMOJI_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def make_auto_reply(author_name, cfg, lang="ko"):
    templates = _cfg_lang(cfg, "auto_reply_templates", lang)
    reply = random.choice(templates).replace("{name}", author_name)
    return strip_specials(reply)   # 이모지 등 특수문자 제외


def make_review_draft(text, author_name, cfg, lang="ko"):
    draft = _cfg_lang(cfg, "review_draft_template", lang)
    return draft.replace("{name}", author_name)


# ─────────────────────────────────────────────
# 답글 게시
# ─────────────────────────────────────────────
def post_reply(youtube, parent_comment_id, text):
    youtube.comments().insert(
        part="snippet",
        body={"snippet": {"parentId": parent_comment_id, "textOriginal": text}},
    ).execute()


# ─────────────────────────────────────────────
# 검토 목록 HTML 생성 (채널별)
# ─────────────────────────────────────────────
def write_review_html(channel_name, review_items, cfg):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for it in review_items:
        rows.append(f"""
        <div class="card">
          <div class="meta">👤 <b>{html.escape(it['author'])}</b> · <span class="reason">{html.escape(it['reason'])}</span></div>
          <div class="comment">{html.escape(it['text'])}</div>
          <div class="draft"><span class="label">답글 초안</span>{html.escape(it['draft'])}</div>
          <a class="btn" href="{html.escape(it['link'])}" target="_blank">유튜브에서 답글 달기 →</a>
        </div>""")
    if not rows:
        rows.append('<p class="empty">검토가 필요한 댓글이 없습니다. 👍</p>')

    doc = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>[{html.escape(channel_name)}] 검토가 필요한 댓글</title>
<style>
  body {{ font-family: -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
         background:#f5f6f8; color:#1a1a1a; margin:0; padding:16px; }}
  h1 {{ font-size:20px; }}
  .ch {{ display:inline-block; background:#ff0000; color:#fff; font-size:13px; font-weight:700;
         padding:3px 10px; border-radius:20px; margin-bottom:8px; }}
  .sub {{ color:#666; font-size:13px; margin-bottom:16px; }}
  .card {{ background:#fff; border-radius:14px; padding:16px; margin-bottom:12px;
           box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .meta {{ font-size:13px; color:#444; margin-bottom:8px; }}
  .reason {{ color:#c0392b; }}
  .comment {{ font-size:15px; line-height:1.5; background:#f0f2f5; border-radius:10px;
              padding:10px 12px; white-space:pre-wrap; }}
  .draft {{ font-size:14px; color:#333; margin:10px 0; padding:10px 12px;
            border-left:3px solid #4a90d9; background:#eef4fb; border-radius:6px; white-space:pre-wrap; }}
  .label {{ display:block; font-size:11px; color:#4a90d9; font-weight:700; margin-bottom:4px; }}
  .btn {{ display:inline-block; background:#ff0000; color:#fff; text-decoration:none;
          padding:9px 14px; border-radius:9px; font-size:14px; font-weight:600; }}
  .empty {{ text-align:center; color:#888; padding:40px 0; }}
</style></head>
<body>
  <div class="ch">📺 {html.escape(channel_name)}</div>
  <h1>🔍 검토가 필요한 댓글</h1>
  <div class="sub">생성 시각: {now} · 총 {len(review_items)}건 · 아래 버튼을 누르면 유튜브에서 바로 답글을 달 수 있어요.</div>
  {''.join(rows)}
</body></html>"""

    # 로컬 저장 (채널명 구분)
    local_path = os.path.join(BASE_DIR, f"검토필요_{safe_name(channel_name)}.html")
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(doc)

    # 폰에서 볼 수 있도록 클라우드(구글 드라이브 등) 폴더에도 채널별로 복사
    sync_base = (cfg or {}).get("mobile_sync_folder", "").strip()
    if sync_base:
        try:
            sync_dir = os.path.join(sync_base, safe_name(channel_name))
            os.makedirs(sync_dir, exist_ok=True)
            shutil.copy2(local_path, os.path.join(sync_dir, "검토필요.html"))
        except Exception as e:
            print(f"    [폰 동기화 실패] {e}")


def write_dashboard(cfg, all_reviews, channel_summaries):
    """모든 채널의 검토 댓글 + 요약을 하나의 대시보드 HTML로 만들어 클라우드에 저장 (폰에서 열기)."""
    sync_base = (cfg or {}).get("mobile_sync_folder", "").strip()
    index_out = os.environ.get("DASHBOARD_INDEX", "").strip()   # 클라우드: GitHub Pages 의 index.html 경로
    if not sync_base and not index_out:
        return
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    total_review = len(all_reviews)
    total_posted = sum(c.get("posted", 0) for c in channel_summaries)

    by_ch = {}
    for it in all_reviews:
        by_ch.setdefault(it.get("channel", ""), []).append(it)

    sections = []
    for c in channel_summaries:
        name = c.get("name", "")
        is_post = c.get("auto")
        mode = "게시" if is_post else "검토만"
        items = by_ch.get(name, [])
        cards = []
        for it in items:
            cards.append(
                f'<div class="card"><div class="meta">👤 <b>{html.escape(it.get("author",""))}</b> · '
                f'<span class="reason">{html.escape(it.get("reason",""))}</span></div>'
                f'<div class="comment">{html.escape(it.get("text",""))}</div>'
                f'<a class="btn" href="{html.escape(it.get("link",""))}" target="_blank">유튜브에서 답글 달기 →</a></div>')
        if not cards:
            cards.append('<p class="empty">검토할 댓글 없음 👍</p>')
        sections.append(
            f'<section><div class="chhead"><span class="ch">📺 {html.escape(name)}</span>'
            f'<span class="tag {"post" if is_post else "rev"}">{mode}</span>'
            f'<span class="cnt">검토 {len(items)}건</span></div>{"".join(cards)}</section>')

    doc = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>유튜브 댓글 대시보드</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;background:#0f1115;color:#e8eaed;margin:0;padding:14px}}
  header{{position:sticky;top:0;background:#0f1115;padding:6px 0 12px;z-index:5}}
  h1{{font-size:19px;margin:0 0 6px}}
  .sum{{font-size:13px;color:#9aa0a6;background:#1a1d24;border-radius:10px;padding:9px 12px}}
  section{{margin:16px 0}}
  .chhead{{display:flex;align-items:center;gap:8px;margin:6px 0 10px}}
  .ch{{font-size:15px;font-weight:800}}
  .tag{{font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px}}
  .tag.post{{background:#1e3a2a;color:#5cd08a}} .tag.rev{{background:#3a1e1e;color:#f08a8a}}
  .cnt{{margin-left:auto;font-size:12px;color:#9aa0a6}}
  .card{{background:#1a1d24;border-radius:14px;padding:14px;margin-bottom:10px}}
  .meta{{font-size:12.5px;color:#c3c7cc;margin-bottom:7px}}
  .reason{{color:#f0a03c}}
  .comment{{font-size:15px;line-height:1.5;background:#0f1115;border-radius:10px;padding:10px 12px;white-space:pre-wrap;margin-bottom:10px}}
  .btn{{display:block;text-align:center;background:#ff0000;color:#fff;text-decoration:none;padding:11px;border-radius:10px;font-size:14.5px;font-weight:700}}
  .empty{{color:#7a8088;text-align:center;padding:16px}}
  footer{{color:#6a7078;font-size:12px;text-align:center;margin:20px 0}}
</style></head>
<body>
<header><h1>📊 유튜브 댓글 대시보드</h1>
<div class="sum">갱신 {now} · 전체 검토 <b>{total_review}</b>건 · 자동답글 게시 <b>{total_posted}</b>건 · 채널 {len(channel_summaries)}개</div></header>
{''.join(sections)}
<footer>30분마다 자동 갱신 · 새로고침하면 최신 반영</footer>
</body></html>"""
    if index_out:
        try:
            with open(index_out, "w", encoding="utf-8") as f:
                f.write(doc)
        except Exception as e:
            print(f"[index.html 저장 실패] {e}")
    if not sync_base:
        return
    try:
        os.makedirs(sync_base, exist_ok=True)
        with open(os.path.join(sync_base, "대시보드.html"), "w", encoding="utf-8") as f:
            f.write(doc)
        # 로컬 웹서버 링크용 영문 파일명 사본 (깔끔한 URL)
        with open(os.path.join(sync_base, "dashboard.html"), "w", encoding="utf-8") as f:
            f.write(doc)
    except Exception as e:
        print(f"[대시보드 저장 실패] {e}")


# ─────────────────────────────────────────────
# 채널 1개 처리
# ─────────────────────────────────────────────
def process_channel(ch, cfg):
    """반환: (자동답글수, 검토수, 건너뜀수, 상태문자열)"""
    name = ch.get("name", "채널")
    youtube = get_service(ch.get("token", ""))
    if youtube is None:
        print(f"[{name}] 인증 없음/만료 → 건너뜀 (채널추가.bat 로 인증 필요)")
        return 0, 0, 0, 0, "인증필요", False, []

    channel_id, title = get_my_channel(youtube)
    if not channel_id:
        print(f"[{name}] 채널 정보를 찾을 수 없음 → 건너뜀")
        return 0, 0, 0, 0, "채널없음", False, []

    # 채널별 auto_post 설정이 있으면 그것을 우선, 없으면 전역 config 값
    auto_post = ch.get("auto_post", cfg.get("auto_post", False))
    max_count = cfg.get("max_comments_per_run", 50)
    # 채널 기본 언어(ko/en/ja). 영어 채널(@petzzangs 등)은 channels.json 에 "lang": "en", 일본어 채널(@人生の便り)은 "ja".
    channel_lang = (ch.get("lang") or "ko").lower()
    match_lang = cfg.get("match_comment_language", True)

    done_ids = load_done_ids(ch)
    threads = fetch_comment_threads(youtube, channel_id, max_count)

    review_items = []
    auto_done = 0       # 실제로 게시한 수
    auto_planned = 0    # 자동답글 대상으로 분류된 수(미리보기 포함)
    skipped = 0

    for th in threads:
        top = th["snippet"]["topLevelComment"]
        comment_id = top["id"]
        sn = top["snippet"]
        author = sn.get("authorDisplayName", "구독자")
        author_id = sn.get("authorChannelId", {}).get("value")
        text = sn.get("textDisplay", "") or sn.get("textOriginal", "")
        video_id = th["snippet"].get("videoId", "")
        link = f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}" if video_id else \
               f"https://www.youtube.com/comment?lc={comment_id}"

        if author_id == channel_id:
            continue
        if comment_id in done_ids:
            skipped += 1
            continue
        if owner_already_replied(th, channel_id):
            done_ids.add(comment_id)
            skipped += 1
            continue

        lang = comment_lang(text, channel_lang) if match_lang else channel_lang
        kind, reason = classify(text, cfg, lang)

        if kind == "auto":
            auto_planned += 1
            reply = make_auto_reply(author, cfg, lang)
            if auto_post:
                try:
                    post_reply(youtube, comment_id, reply)
                    done_ids.add(comment_id)
                    auto_done += 1
                    print(f"  [자동답글✅] {author}: {text[:24]}...")
                except HttpError as e:
                    print(f"  [오류] {author} 답글 실패: {e}")
            else:
                print(f"  [자동답글 예정👀] {author}: {text[:24]}...  ({reason})")
        else:
            draft = make_review_draft(text, author, cfg, lang)
            review_items.append({
                "author": author, "text": text, "reason": reason,
                "draft": draft, "link": link, "comment_id": comment_id,
            })
            print(f"  [검토필요🔍] {author}: {text[:24]}...  ({reason})")

    write_review_html(title or name, review_items, cfg)
    save_done_ids(ch, done_ids)
    return auto_done, auto_planned, len(review_items), skipped, "완료", auto_post, review_items


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def main():
    cfg = load_config()
    channels = load_channels()

    print("=" * 52)
    print("유튜브 댓글 도우미 (멀티 채널) 실행")
    print(f"관리 채널 수: {len(channels)}개 (자동답글 여부는 채널별 설정 적용)")
    print("=" * 52)

    if not channels:
        print("등록된 채널이 없습니다. '채널추가.bat' 을 실행해 채널을 먼저 추가하세요.")
        return

    total_posted = total_planned = total_review = 0
    summaries = []
    all_reviews = []
    channel_summaries = []
    for ch in channels:
        name = ch.get("name", "채널")
        print(f"\n── [{name}] 처리 중 ──")
        try:
            posted, planned, r, s, status, ch_auto, reviews = process_channel(ch, cfg)
        except HttpError as e:
            print(f"[{name}] API 오류 → 건너뜀: {e}")
            posted, planned, r, s, status, ch_auto, reviews = 0, 0, 0, 0, "API오류", False, []
        for it in reviews:
            it["channel"] = name
            all_reviews.append(it)
        channel_summaries.append({"name": name, "auto": ch_auto, "posted": posted, "review": r})
        total_posted += posted
        total_planned += planned
        total_review += r
        mode = "게시" if ch_auto else "검토만"
        if ch_auto:
            summaries.append(f"{name}[{mode}](답글{posted}/검토{r})")
        else:
            summaries.append(f"{name}[{mode}](검토{r})")

    print("\n" + "=" * 52)
    print("전체 완료 요약")
    print(f"  자동답글 게시됨: {total_posted}건 (미리보기/검토전용 대상 {total_planned}건)")
    print(f"  검토필요: {total_review}건  ->  채널별 검토필요.html 확인")
    print("=" * 52)

    try:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(RUN_LOG_PATH, "a", encoding="utf-8") as lf:
            lf.write(f"[{stamp}] 채널:{len(channels)} | 총게시:{total_posted} | 총검토:{total_review} | {' '.join(summaries)}\n")
    except Exception:
        pass

    # 통합 대시보드 HTML 생성 (구글 드라이브 + GitHub Pages)
    try:
        write_dashboard(cfg, all_reviews, channel_summaries)
    except Exception as e:
        print(f"[대시보드 생성 오류] {e}")

    # 최신 대시보드를 GitHub Pages로 즉시 푸시 (알림 링크가 항상 최신)
    try:
        push_dashboard(cfg)
    except Exception as e:
        print(f"[Pages 푸시 오류] {e}")

    # 검토 필요 새 댓글 → 폰 텔레그램 알림(댓글 미리보기 + 대시보드 링크)
    try:
        notify_review(cfg, all_reviews)
    except Exception as e:
        print(f"[알림 처리 오류] {e}")


if __name__ == "__main__":
    main()
