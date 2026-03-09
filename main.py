from scripts.algumon_parser import fetch_algumon_deals, load_sent_deals, save_sent_deal, init_db
from scripts.eomisae_parser import fetch_eomisae_deals
from scripts.ppomppu_parser import fetch_ppomppu_deals
from scripts.formatter import identify_shop, convert_to_affiliate_link, generate_tweet_text, get_ai_description
from scripts.telegram_publisher import send_message as tg_send, format_telegram_message, is_configured as tg_ok
import tweepy
import os
import time
import random
import schedule
import logging
import sqlite3
from dotenv import load_dotenv

load_dotenv()

# ── 로깅 설정 ──────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "bot.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("hotdeal_bot")

# ── 트위터 API 설정 ────────────────────────────────────
client = tweepy.Client(
    bearer_token=os.getenv("X_BEARER_TOKEN"),
    consumer_key=os.getenv("X_CONSUMER_KEY"),
    consumer_secret=os.getenv("X_CONSUMER_SECRET"),
    access_token=os.getenv("X_ACCESS_TOKEN"),
    access_token_secret=os.getenv("X_ACCESS_SECRET")
)

# ── X API 무료 플랜 일 한도 관리 ──────────────────────
MAX_TWEETS_PER_DAY = int(os.getenv("MAX_TWEETS_PER_DAY", "45"))
DB_FILE = os.path.join(os.path.dirname(__file__), "data", "deals.db")


def _get_today_tweet_count() -> int:
    """오늘 발행한 트윗 수를 DB에서 조회합니다."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM sent_deals WHERE DATE(sent_at) = DATE('now', 'localtime')"
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


def _publish_to_twitter(deal: dict, main_tweet: str, reply_tweet: str) -> bool:
    """트위터에 메인 트윗 + 공정위 답글을 발행합니다."""
    try:
        response = client.create_tweet(text=main_tweet)
        tweet_id = response.data['id']
        if tweet_id:
            client.create_tweet(text=reply_tweet, in_reply_to_tweet_id=tweet_id)
            log.info(f"[트위터] 발행 성공 ID={tweet_id} | {deal['title'][:30]}")
            return True
    except tweepy.errors.TooManyRequests:
        log.error("[트위터] 속도 제한 도달. 10분 대기.")
        time.sleep(600)
    except Exception as e:
        log.error(f"[트위터] 발행 에러: {e}")
    return False


def _publish_to_telegram(deal: dict, converted_link: str, ai_desc: str) -> bool:
    """텔레그램 채널에 핫딜을 발행합니다."""
    if not tg_ok():
        return False
    msg = format_telegram_message(deal, converted_link, ai_desc)
    ok = tg_send(msg)
    if ok:
        log.info(f"[텔레그램] 발행 성공 | {deal['title'][:30]}")
    return ok


def run_bot():
    log.info("── 핫딜 크롤링 사이클 시작 ──")

    # ── 트위터 API 일 한도 체크 ───────────────────────
    today_count = _get_today_tweet_count()
    twitter_remaining = max(0, MAX_TWEETS_PER_DAY - today_count)
    log.info(f"오늘 트위터 발행: {today_count}건 / 한도: {MAX_TWEETS_PER_DAY}건 (잔여 {twitter_remaining}건)")

    sent_deals = load_sent_deals()
    all_deals = []

    # 1. 알구몬 크롤링
    try:
        algumon_deals = fetch_algumon_deals()
        all_deals.extend(algumon_deals)
        log.info(f"알구몬: {len(algumon_deals)}개")
    except Exception as e:
        log.error(f"알구몬 파싱 오류: {e}")

    # 2. 어미새 크롤링
    try:
        eomisae_deals = fetch_eomisae_deals()
        all_deals.extend(eomisae_deals)
        log.info(f"어미새: {len(eomisae_deals)}개")
    except Exception as e:
        log.error(f"어미새 파싱 오류: {e}")

    # 3. 뽐뿌 크롤링
    try:
        ppomppu_deals = fetch_ppomppu_deals()
        all_deals.extend(ppomppu_deals)
        log.info(f"뽐뿌: {len(ppomppu_deals)}개")
    except Exception as e:
        log.error(f"뽐뿌 파싱 오류: {e}")

    # 중복 필터링
    new_deals = [d for d in all_deals if d['id'] not in sent_deals]
    log.info(f"발행 대기 중인 새 핫딜: {len(new_deals)}건")

    for i, deal in enumerate(new_deals):
        shop_type = identify_shop(deal['shop_url'], deal.get('store', ''))
        formatted_link = convert_to_affiliate_link(deal['shop_url'], shop_type)
        ai_desc = get_ai_description(deal['title'], deal['price'])
        main_tweet, reply_tweet = generate_tweet_text(deal, formatted_link, ai_desc)

        published = False

        # ── 트위터 발행 (한도 내) ──
        if twitter_remaining > 0:
            ok = _publish_to_twitter(deal, main_tweet, reply_tweet)
            if ok:
                twitter_remaining -= 1
                published = True

        # ── 텔레그램 발행 (항상, 한도 무관) ──
        tg_published = _publish_to_telegram(deal, formatted_link, ai_desc)
        if tg_published:
            published = True

        # DB에 저장 (트위터 또는 텔레그램 중 하나라도 성공 시)
        if published:
            save_sent_deal(deal['id'], deal['title'], deal['price'], deal['replies'])

        # 섀도우밴 방지 랜덤 딜레이
        time.sleep(random.randint(15, 30))

    log.info("── 사이클 완료 ──\n")


if __name__ == "__main__":
    init_db()
    log.info("핫딜 봇 가동 시작. (15분 주기)")

    run_bot()

    schedule.every(15).minutes.do(run_bot)

    while True:
        schedule.run_pending()
        time.sleep(1)
