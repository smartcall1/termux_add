"""
뽐뿌 핫딜 파서 (해외뽐뿌 게시판 기준).

뽐뿌는 알구몬의 원본 소스 중 하나이므로 알구몬보다 최대 수십분 빠르게 딜을 수집 가능.
HOT 게시물 필터: 추천수 5개 이상 + 댓글 10개 이상을 기준으로 잡음.

크롤링 타겟:
- 해외뽐뿌: https://www.ppomppu.co.kr/zboard/zboard.php?id=o_coupon
- 국내뽐뿌: https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu
"""
import os
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "deals.db")

PPOMPPU_BOARDS = [
    {
        "name": "뽐뿌(해외)",
        "url": "https://www.ppomppu.co.kr/zboard/zboard.php?id=o_coupon",
        "min_recomm": 3,
        "min_replies": 5,
    },
    {
        "name": "뽐뿌(국내)",
        "url": "https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu",
        "min_recomm": 5,
        "min_replies": 10,
    },
]


def fetch_ppomppu_deals() -> list:
    deals = []
    headers = {
        "User-Agent": UserAgent().random,
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://www.ppomppu.co.kr/",
    }

    for board in PPOMPPU_BOARDS:
        try:
            resp = requests.get(board["url"], headers=headers, timeout=12)
            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "html.parser")

            # 뽐뿌 목록 테이블 행 파싱
            rows = soup.select("tr.list1, tr.list0")

            for row in rows:
                try:
                    # 제목 셀
                    title_tag = row.select_one("a.title, td.title a")
                    if not title_tag:
                        continue

                    title = title_tag.text.strip()
                    if not title or len(title) < 5:
                        continue

                    # 링크
                    href = title_tag.get("href", "")
                    if not href:
                        continue
                    if href.startswith("/"):
                        href = "https://www.ppomppu.co.kr" + href

                    # 게시글 ID
                    deal_id = "ppomppu_" + href.split("no=")[-1].split("&")[0] if "no=" in href else "ppomppu_" + href.split("/")[-1]

                    # 추천수
                    recomm_tag = row.select_one("td.list_vspace")
                    recomm = 0
                    if recomm_tag:
                        txt = recomm_tag.text.strip()
                        if "-" in txt:
                            parts = txt.split("-")
                            try:
                                recomm = int(parts[0].strip())
                            except ValueError:
                                pass

                    # 댓글수
                    reply_tag = row.select_one("span.list_comment2, font.list_comment")
                    reply_count = 0
                    if reply_tag:
                        rc_txt = reply_tag.text.strip().replace("[", "").replace("]", "")
                        if rc_txt.isdigit():
                            reply_count = int(rc_txt)

                    # 가격 (제목에서 추출 시도)
                    price = _extract_price_from_title(title)

                    is_hot = recomm >= board["min_recomm"] and reply_count >= board["min_replies"]
                    is_coupang = "쿠팡" in (title or "")
                    
                    if is_hot or is_coupang:
                        deals.append({
                            "id": deal_id,
                            "title": title,
                            "price": price,
                            "replies": reply_count,
                            "site": board["name"],
                            "shop_url": href,  # 뽐뿌 게시글 자체 링크
                            "algumon_url": href,
                        })
                except Exception:
                    continue

        except Exception as e:
            print(f"[뽐뿌 파싱 에러] {board['name']}: {e}")

    return deals


def _extract_price_from_title(title: str) -> str:
    """
    제목에서 가격을 추출합니다.
    예) '맥북프로 M3 ($999)' → '$999'
    """
    import re
    patterns = [
        r'\$[\d,]+(?:\.\d{1,2})?',          # $999, $1,299.99
        r'￦[\d,]+',                          # ￦150,000
        r'[\d,]+원',                          # 150,000원
        r'€[\d,]+(?:\.\d{1,2})?',            # €299
    ]
    for pat in patterns:
        m = re.search(pat, title)
        if m:
            return m.group(0)
    return "링크 내 확인"


if __name__ == "__main__":
    deals = fetch_ppomppu_deals()
    print(f"뽐뿌 파싱 결과: {len(deals)}건")
    for d in deals[:5]:
        print(f"  [{d['site']}] {d['title']} / {d['price']} / 댓글 {d['replies']}개")
        print(f"  링크: {d['shop_url']}")
