"""
텔레그램 채널 자동 발행 모듈.

트위터 API는 무료 플랜 기준 일 50건 한도지만,
텔레그램 Bot API는 사실상 무제한 무료.
→ 트위터 한도 초과분은 텔레그램 채널로만 발행하는 투트랙 전략.

설정 방법:
1. @BotFather → /newbot → 봇 생성 → TELEGRAM_BOT_TOKEN 발급
2. 채널 생성 → 봇을 관리자로 초대
3. 채널 링크에서 채널 ID 확인 (예: @my_hotdeal_channel 또는 -100123456789)
4. .env에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID 추가
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

_BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def is_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID)


def send_message(text: str, photo_url: str = None) -> bool:
    """
    텔레그램 채널에 메시지를 발행합니다.
    photo_url이 있으면 이미지+캡션, 없으면 텍스트 메시지로 발행.
    """
    if not is_configured():
        return False

    try:
        if photo_url:
            resp = requests.post(
                f"{_BASE_URL}/sendPhoto",
                json={
                    "chat_id": TELEGRAM_CHANNEL_ID,
                    "photo": photo_url,
                    "caption": text[:1024],  # 텔레그램 캡션 최대 1024자
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
        else:
            resp = requests.post(
                f"{_BASE_URL}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHANNEL_ID,
                    "text": text[:4096],
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=10,
            )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[텔레그램 발행 에러] {e}")
        return False


def format_telegram_message(deal: dict, converted_link: str, ai_desc: str = "", shop_type: str = "other") -> str:
    """
    텔레그램용 HTML 포맷 메시지 생성.
    트위터보다 긴 텍스트가 허용되므로 더 풍부한 정보 제공.
    """
    title = deal.get("title", "핫딜")
    price = deal.get("price", "")
    replies = deal.get("replies", 0)
    site = deal.get("site", "")

    desc_line = f"\n💬 {ai_desc}\n" if ai_desc else ""

    # 쿠팡(제휴) 딜만 광고 고지 문구 추가
    affiliate_notice = "\n<i>#광고 제휴 링크를 통한 구매 시 수수료가 발생합니다.</i>" if shop_type == 'coupang' else ""

    msg = (
        f"<b>🔥 핫딜 알림</b>\n\n"
        f"<b>{title}</b>\n"
        f"💰 {price}{desc_line}\n"
        f"💬 커뮤니티 반응: {replies}개\n"
        f"🏪 출처: {site}\n\n"
        f"👉 <a href='{converted_link}'>탑승링크 바로가기</a>"
        f"{affiliate_notice}"
    )
    return msg
