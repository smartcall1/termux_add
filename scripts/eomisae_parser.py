"""
어미새(eomisae.co.kr) 핫딜 파서.

파싱 방식:
- /fs 게시판의 a 태그에서 /fs/숫자 패턴 링크 추출
- 같은 게시글의 댓글 링크(/fs/숫자#C_)가 바로 뒤에 오는 구조를 활용해 댓글 수 추출
- "Read More" / 공지 등 고정글(숫자 ID < 1000000) 제외
"""
import os
import re
import requests
import sqlite3
from bs4 import BeautifulSoup

EOMISAE_URL = "https://eomisae.co.kr/fs"
DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "deals.db")

# 공지/이벤트 고정글 ID (변경 거의 없음)
PINNED_IDS = {"915341", "2108073"}


def load_sent_deals():
    if not os.path.exists(DB_FILE):
        return []
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM sent_deals")
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def fetch_eomisae_deals(min_replies: int = 5) -> list:
    """
    어미새 /fs 게시판에서 핫딜을 파싱합니다.

    min_replies: 최소 댓글 수 기준 (기본값 5)
    """
    deals = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://eomisae.co.kr/",
    }

    try:
        response = requests.get(EOMISAE_URL, headers=headers, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        all_links = soup.find_all("a", href=True)

        i = 0
        while i < len(all_links):
            a = all_links[i]
            href = a["href"]

            # 게시글 링크 패턴: /fs/숫자 (끝이 숫자로만 끝나야 함)
            m = re.match(r"^/fs/(\d+)$", href)
            if not m:
                i += 1
                continue

            post_id = m.group(1)

            # 공지/이벤트 고정글 제외
            if post_id in PINNED_IDS:
                i += 1
                continue

            title = a.text.strip()

            # "Read More" 같은 더보기 버튼 제외
            if not title or len(title) < 4 or title.lower() in ("read more", "더보기", "..."):
                i += 1
                continue

            # 다음 링크가 같은 게시글의 댓글 앵커인지 확인 → 댓글 수 추출
            reply_count = 0
            if i + 1 < len(all_links):
                next_a = all_links[i + 1]
                next_href = next_a["href"]
                if next_href.startswith(href + "#"):
                    rc_text = next_a.text.strip()
                    if rc_text.isdigit():
                        reply_count = int(rc_text)
                    i += 1  # 댓글 링크는 소비

            is_coupang = "쿠팡" in (title or "")
            if not is_coupang and reply_count < min_replies:
                i += 1
                continue

            # 썸네일 이미지 추출 시도
            thumbnail_url = ""
            try:
                # 어미새는 보통 tr 내부에 별도 td나 div로 썸네일이 있음. 
                # 여기선 tr 내부의 img 태그를 찾아봄
                parent_row = a.find_parent("tr")
                if parent_row:
                    img_tag = parent_row.select_one("img")
                    if img_tag and img_tag.get("src"):
                        thumbnail_url = img_tag.get("src")
                        if not thumbnail_url.startswith("http"):
                            thumbnail_url = "https://eomisae.co.kr" + thumbnail_url
            except Exception:
                pass

            deal_id = f"eomisae_{post_id}"
            full_url = f"https://eomisae.co.kr{href}"

            deals.append({
                "id": deal_id,
                "title": title,
                "price": "링크 내 확인",
                "replies": reply_count,
                "site": "어미새",
                "store": "",
                "shop_url": full_url,
                "thumbnail_url": thumbnail_url,
                "algumon_url": full_url,
            })

            i += 1

    except Exception as e:
        print(f"어미새 파싱 에러: {e}")

    # 댓글 많은 순 정렬
    deals.sort(key=lambda x: x["replies"], reverse=True)
    return deals


if __name__ == "__main__":
    print("🚀 어미새 핫딜 크롤러 테스트")
    found = fetch_eomisae_deals(min_replies=1)
    sent = load_sent_deals()

    print(f"전체 파싱: {len(found)}개\n" + "-" * 50)
    for d in found:
        status = "🆕" if d["id"] not in sent else "✅"
        print(f"{status} [💬{d['replies']}] {d['title'][:55]} | 🖼 {bool(d['thumbnail_url'])}")
        if d['thumbnail_url']:
            print(f"   🖼 {d['thumbnail_url'][:60]}...")
        print(f"   🔗 {d['shop_url']}")
        print()
