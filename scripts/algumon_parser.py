"""
알구몬(algumon.com) 핫딜 파서.

2026-03 사이트 구조 변경 대응:
- 이전: Next.js / /category/1/hot → __NEXT_DATA__
- 현재: SvelteKit / /n/deal → __data.json API 엔드포인트

SvelteKit __data.json 구조:
  nodes[1].data = flat array
  data[0] = 페이지 메타 (deals 필드 = 인덱스 1)
  data[1] = pagination 객체 (contents = 인덱스 2)
  data[2] = 딜 인덱스 목록 배열 [3, 22, 36, ...]
  data[N] = 딜 스키마 객체 (필드값이 int이면 인덱스 참조)

크롤링 소스 (쿠팡 딜 최대화):
  1. /n/deal      — 최신 핫딜 피드
  2. /n/deal/rank — 랭킹(인기) 핫딜 피드
  두 피드를 합산 후 id 기준 중복 제거
"""
import os
import requests
import sqlite3

ALGUMON_URLS = [
    "https://www.algumon.com/n/deal/__data.json",
    "https://www.algumon.com/n/deal/rank/__data.json",
]
DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "deals.db")


def _resolve(arr: list, val):
    """SvelteKit flat array 인덱스 참조 해석. int이면 인덱스로 조회, 아니면 그대로."""
    if isinstance(val, int) and 0 <= val < len(arr):
        return arr[val]
    return val


def init_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sent_deals (
            id TEXT PRIMARY KEY,
            title TEXT,
            price TEXT,
            replies INTEGER,
            shop_type TEXT DEFAULT 'unknown',
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # 기존 DB에 shop_type 컬럼이 없으면 추가 (무중단 마이그레이션)
    try:
        cursor.execute("ALTER TABLE sent_deals ADD COLUMN shop_type TEXT DEFAULT 'unknown'")
    except sqlite3.OperationalError:
        pass  # 이미 존재하면 무시
    conn.commit()
    conn.close()


def load_sent_deals():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM sent_deals")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def save_sent_deal(deal_id, title, price, replies, shop_type="unknown"):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO sent_deals (id, title, price, replies, shop_type) VALUES (?, ?, ?, ?, ?)",
        (str(deal_id), title, price, replies, shop_type)
    )
    conn.commit()
    conn.close()


def _parse_one_feed(url: str, min_comments: int, headers: dict) -> list:
    """단일 알구몬 __data.json 피드를 파싱해 딜 목록 반환."""
    deals = []
    try:
        response = requests.get(url, headers=headers, timeout=12)
        response.raise_for_status()
        raw = response.json()

        nodes = raw.get("nodes", [])
        if len(nodes) < 2:
            print(f"❌ 알구몬({url}): nodes 구조 예상과 다름")
            return deals

        arr = nodes[1].get("data", [])
        if len(arr) < 3:
            print(f"❌ 알구몬({url}): data array 너무 짧음")
            return deals

        deal_indices = arr[2]
        if not isinstance(deal_indices, list):
            print(f"❌ 알구몬({url}): 딜 인덱스 배열을 찾지 못함")
            return deals

        for idx in deal_indices:
            try:
                schema = arr[idx]
                if not isinstance(schema, dict):
                    continue

                deal_id   = _resolve(arr, schema.get("id"))
                site_name = _resolve(arr, schema.get("siteName", ""))
                store     = _resolve(arr, schema.get("storeName", ""))
                title     = _resolve(arr, schema.get("title", ""))
                price     = _resolve(arr, schema.get("price", ""))
                shop_url  = _resolve(arr, schema.get("originalUrl", ""))
                comments  = _resolve(arr, schema.get("commentCount", 0))
                ended     = _resolve(arr, schema.get("ended", False))
                thumbnail = _resolve(arr, schema.get("thumbnailUrl", ""))

                if ended:
                    continue
                if not isinstance(title, str) or not title.strip():
                    continue
                if not isinstance(comments, int):
                    comments = 0
                if comments < min_comments:
                    continue

                deals.append({
                    "id": str(deal_id),
                    "title": title.strip(),
                    "price": str(price) if price else "링크 내 확인",
                    "replies": comments,
                    "site": str(site_name),
                    "store": str(store) if store else "",
                    "shop_url": str(shop_url) if shop_url else "",
                    "thumbnail_url": str(thumbnail) if thumbnail else "",
                    "algumon_url": f"https://www.algumon.com/n/deal/{deal_id}",
                })
            except (IndexError, TypeError, KeyError):
                continue

    except Exception as e:
        print(f"알구몬 파싱 에러({url}): {e}")

    return deals


def fetch_algumon_deals(min_comments: int = 1) -> list:
    """
    알구몬 일반(/n/deal) + 랭킹(/n/deal/rank) 두 피드를 합산해
    진행 중인 핫딜을 파싱합니다. id 기준 중복 제거.

    min_comments: 최소 댓글 수 기준 (기본값 1 — 반응 있는 딜만)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Accept": "application/json",
    }

    seen_ids: set = set()
    merged: list = []

    for url in ALGUMON_URLS:
        for deal in _parse_one_feed(url, min_comments, headers):
            if deal["id"] not in seen_ids:
                seen_ids.add(deal["id"])
                merged.append(deal)

    return merged


if __name__ == "__main__":
    print("🚀 알구몬 핫딜 크롤러 테스트 (일반 + 랭킹 합산)")
    init_db()

    found = fetch_algumon_deals(min_comments=0)
    sent = load_sent_deals()
    new_deals = [d for d in found if d["id"] not in sent]

    coupang_deals = [d for d in found if "쿠팡" in d.get("store", "") or "쿠팡" in d.get("site", "")]
    print(f"전체 파싱: {len(found)}개 / 새 딜: {len(new_deals)}개 / 쿠팡: {len(coupang_deals)}개\n" + "-" * 50)
    for d in found:
        status = "🆕" if d["id"] not in sent else "✅"
        coupang_mark = " 🛒쿠팡" if "쿠팡" in d.get("store", "") or "쿠팡" in d.get("site", "") else ""
        print(f"{status}{coupang_mark} [{d['site']}→{d['store']}] {d['title'][:50]}")
        print(f"   💰{d['price']} | 💬{d['replies']}개 | 🖼{bool(d['thumbnail_url'])}")
        print(f"   🔗 {d['shop_url'][:80]}")
        print()
