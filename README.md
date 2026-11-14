# 유튜브 댓글봇 (클라우드)

PC가 꺼져 있어도 GitHub Actions가 대신 실행합니다.

- **댓글봇**: 30분마다(매시 7분·37분) — 감사 댓글 자동답글, 나머지는 검토 목록 + 텔레그램 알림
- **채널 대시보드**: 1시간마다(매시 7분)
- 폰 링크
  - 댓글 검토: https://ykwanghee-lab.github.io/yt-comment-bot/
  - 채널 현황: https://ykwanghee-lab.github.io/yt-comment-bot/channels.html

## 폴더
- `bot/` 댓글봇 코드·설정(config.json, channels.json)·처리기록(이미처리한댓글_*.json)·실행기록(run_log.txt)
- `dash/` 채널 대시보드 코드·통계 기록
- `.github/workflows/bot.yml` 자동 실행 시간표

## 비밀값
채널 로그인 토큰과 텔레그램 토큰은 저장소 파일이 아니라 **Settings → Secrets → BOT_SECRETS** 에만 있습니다.
채널을 새로 추가하거나 재인증하면 PC의 `D:\0000_프로그램들\유튜브댓글자동봇` 에서 인증한 뒤 BOT_SECRETS 를 다시 올려야 합니다.

## 수동 실행
Actions 탭 → comment-bot → Run workflow
