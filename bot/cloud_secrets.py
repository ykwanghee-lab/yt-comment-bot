# -*- coding: utf-8 -*-
"""GitHub Actions 전용: 저장소 비밀값(BOT_SECRETS)을 실행 때만 파일로 풀어 놓는다.

BOT_SECRETS 형식(JSON):
  {"config": {"telegram_token": "..."},
   "tokens": {"token_사연이짱.json": {...}, ...}}

풀어 놓은 파일(token_*.json, secret_config.json)은 .gitignore 로 저장소에 절대 올라가지 않는다.
비밀값이 없으면 ready=false 를 내보내 뒤 단계(댓글 처리·대시보드)를 건너뛴다
(빈 대시보드로 덮어쓰는 사고 방지).
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def set_output(ready):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"ready={'true' if ready else 'false'}\n")


def main():
    raw = (os.environ.get("BOT_SECRETS") or "").strip()
    if not raw:
        print("BOT_SECRETS 비밀값이 없습니다 → 이번 실행은 건너뜁니다.")
        set_output(False)
        return
    try:
        data = json.loads(raw)
    except Exception as e:
        print(f"BOT_SECRETS 형식 오류: {e}")
        set_output(False)
        sys.exit(1)

    tokens = data.get("tokens", {})
    for name, content in tokens.items():
        if os.path.basename(name) != name or not name.startswith("token_"):
            print(f"이상한 토큰 파일명 건너뜀: {name!r}")
            continue
        with open(os.path.join(BASE_DIR, name), "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)
    with open(os.path.join(BASE_DIR, "secret_config.json"), "w", encoding="utf-8") as f:
        json.dump(data.get("config", {}), f, ensure_ascii=False)
    print(f"토큰 {len(tokens)}개 준비 완료")
    set_output(True)


if __name__ == "__main__":
    main()
