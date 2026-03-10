import re
import os
import random
import hmac
import hashlib
import time as _time
import requests as _req
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# 제휴 마케팅 설정 (환경 변수에서 로드)
AFFILIATE_CONFIG = {
    'coupang': {
        'access_key': os.getenv("COUPANG_ACCESS_KEY"),
        'secret_key': os.getenv("COUPANG_SECRET_KEY"),
        'af_id': os.getenv("COUPANG_AF_ID")
    },
    'aliexpress': {
        'app_key': os.getenv("ALI_APP_KEY"),
        'app_secret': os.getenv("ALI_APP_SECRET"),
        'tracking_id': os.getenv("ALI_TRACKING_ID")
    },
    'amazon': {
        'access_key': os.getenv("AMAZON_ACCESS_KEY"),
        'secret_key': os.getenv("AMAZON_SECRET_KEY"),
        'tag': os.getenv("AMAZON_TAG")
    },
    'temu': {
        'app_key': os.getenv("TEMU_APP_KEY"),
        'app_secret': os.getenv("TEMU_APP_SECRET"),
        'tracking_id': os.getenv("TEMU_TRACKING_ID"),
        'invite_code': os.getenv("TEMU_INVITE_CODE")
    }
}

# Gemini API 설정 (환경 변수에서 API 키 로드)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    model = None

_AI_STYLES = [
    {
        "name": "호들갑",
        "desc": "과장되게 흥분한 스타일로 써. 예: '미쳤다', '뇌정지옴', 'ㄹㅇ 역대급'. 이모지 2개.",
        "ex_intro": "🤯 뇌정지옴 이게 이 가격?!",
        "ex_body": "역대급 대란 확정임;; 안 사면 흑우 각",
    },
    {
        "name": "냉철 팩폭",
        "desc": "조용하지만 팩트로 꽂히는 스타일로 써. 예: '그냥 사라', '이유 없다', '묻고 더블로'. 이모지 1개.",
        "ex_intro": "🎯 그냥 사라. 이유 없다.",
        "ex_body": "이 가격에 이 품질이면 더 이상 고민할 게 없음",
    },
    {
        "name": "갓생러",
        "desc": "절약/가성비를 강조하는 갓생 스타일로 써. 예: '이거면 이번달 버팀', '지갑 걱정 끝'. 이모지 1개.",
        "ex_intro": "💰 지갑 걱정 끝났다",
        "ex_body": "월 생활비 아끼려면 이런 딜 놓치면 안 됨;;",
    },
    {
        "name": "커뮤 밈",
        "desc": "인터넷 커뮤니티 말투로 써. 예: 'ㅇㅈ?ㅇㅈ', '이건 알고가', '개꿀ㅋ', '존버 끝'. 이모지 1개.",
        "ex_intro": "👀 이건 알고가야 함 ㄹㅇ",
        "ex_body": "커뮤에서 난리난 거 드디어 직접 확인함 개꿀ㅋ",
    },
    {
        "name": "드라마틱",
        "desc": "짧은 스토리텔링 스타일로 써. 예: '오늘 아침에 발견했는데..', '지인한테만 알려줌'. 이모지 1개.",
        "ex_intro": "🤫 지인한테만 살짝 알려줌",
        "ex_body": "이거 나만 알고 싶었는데 그냥 퍼뜨린다",
    },
]

def get_ai_description(title, price):
    """
    Gemini API로 스타일 페르소나를 랜덤 선택해 인트로+설명 2줄을 생성합니다.
    반환: (intro_line, desc_line) 튜플. 실패 시 (None, "")
    """
    if not model:
        return None, ""

    style = random.choice(_AI_STYLES)

    prompt = f"""
너는 트위터/X 핫딜 알림 계정 운영자야.
오늘은 반드시 '{style["name"]}' 스타일로만 써야 해.

[{style["name"]} 스타일 규칙]
{style["desc"]}

[제품 정보]
- 상품명: {title}
- 가격: {price}

[출력 형식]
- 첫 줄: 강렬한 후크 문장 (30자 이내, {style["name"]} 스타일 필수)
- 둘째 줄: 핵심 장점 또는 지금 사야 하는 이유 (40자 이내, 구어체 ~함/~임;;)
- 딱 2줄만. 번호/따옴표/설명 없이 본문만.

[예시]
{style["ex_intro"]}
{style["ex_body"]}
"""
    try:
        response = model.generate_content(prompt)
        lines = [l.strip() for l in response.text.strip().replace('"', '').splitlines() if l.strip()]
        if len(lines) >= 2:
            return lines[0], lines[1]
        elif len(lines) == 1:
            return lines[0], ""
        return None, ""
    except Exception as e:
        print(f"Gemini API 에러: {e}")
        return None, ""

_SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _resolve_algumon_to_coupang(algumon_url: str) -> str | None:
    """
    알구몬 /l/d/ 리다이렉트 URL에서 실제 coupang.com 상품 URL을 추출합니다.

    흐름:
      1. algumon /l/d/ 페이지 → window.location.href → 포럼 URL
      2. 포럼 페이지 HTML에서 coupang.com/vp/products/ URL 정규식 추출
    """
    try:
        r = _req.get(algumon_url, headers=_SCRAPE_HEADERS, timeout=8)
        m = re.search(r"window\.location\.href\s*=\s*[\"'](https?://[^\"']+)[\"']", r.text)
        if not m:
            return None
        forum_url = m.group(1)

        r2 = _req.get(forum_url, headers=_SCRAPE_HEADERS, timeout=8)
        # 쿠팡 상품 URL 우선순위: /vp/products/ > pages.coupang.com > 기타 coupang.com
        for pattern in [
            r"https://www\.coupang\.com/vp/products/[^\s\"'<>]+",
            r"https://[a-z]+\.coupang\.com/[^\s\"'<>]+",
        ]:
            found = re.findall(pattern, r2.text)
            if found:
                # 가장 짧은(깔끔한) URL 반환
                return min(found, key=len)
    except Exception as e:
        print(f"[알구몬 URL 해석 에러] {e}")
    return None


def extract_coupang_from_post(post_url: str) -> str | None:
    """
    어미새/뽐뿌 게시글 URL을 직접 크롤링해 본문 내 쿠팡 상품 URL을 추출합니다.
    우선순위: /vp/products/ > link.coupang.com > 기타 coupang.com
    """
    try:
        r = _req.get(post_url, headers=_SCRAPE_HEADERS, timeout=10)
        r.encoding = r.apparent_encoding  # 뽐뿌 EUC-KR 대응
        for pattern in [
            r"https://www\.coupang\.com/vp/products/[^\s\"'<>&]+",
            r"https://link\.coupang\.com/[^\s\"'<>&]+",
            r"https://[a-z]+\.coupang\.com/[^\s\"'<>&]+",
        ]:
            found = re.findall(pattern, r.text)
            if found:
                return min(found, key=len)
    except Exception as e:
        print(f"[게시글 쿠팡 링크 추출 에러] {post_url[:60]} | {e}")
    return None


def identify_shop(url, store=""):
    """
    URL 또는 storeName 필드로 어떤 쇼핑몰인지 식별합니다.
    store 필드가 있으면 우선 사용 (알구몬 리다이렉트 URL 대응).
    """
    store_lower = store.lower()
    if "쿠팡" in store_lower or "coupang" in store_lower:
        return "coupang"

    if not url:
        return "unknown"

    url_lower = url.lower()
    if "coupang.com" in url_lower:
        return "coupang"
    elif "aliexpress.com" in url_lower or "a.aliexpress.com" in url_lower:
        return "aliexpress"
    elif "amazon.com" in url_lower or "amzn.to" in url_lower:
        return "amazon"
    elif "temu.com" in url_lower:
        return "temu"
    else:
        return "other"

def _generate_coupang_link(product_url):
    """
    쿠팡 파트너스 HMAC-SHA256 서명 기반 딥링크 생성.

    product_url이 algumon.com/l/d/ 리다이렉트이면:
      → 포럼 페이지까지 타고 들어가 실제 coupang.com URL 추출
    Access Key + Secret Key가 없으면 원본 URL 그대로 반환.
    """
    cfg = AFFILIATE_CONFIG['coupang']
    access_key = cfg.get('access_key')
    secret_key = cfg.get('secret_key')
    af_id = cfg.get('af_id')

    if not all([access_key, secret_key, af_id]):
        return product_url

    # 알구몬 리다이렉트 URL이면 실제 쿠팡 URL 추출
    actual_url = product_url
    if "algumon.com/l/d/" in product_url:
        resolved = _resolve_algumon_to_coupang(product_url)
        if resolved:
            print(f"[쿠팡 URL 해석] {product_url[:60]} → {resolved[:80]}")
            actual_url = resolved
        else:
            print(f"[쿠팡 URL 해석 실패] 알구몬 리다이렉트 미해결, 원본 사용")

    REQUEST_METHOD = "GET"
    REQUEST_PATH = "/v2/providers/affiliate_open_api/apis/openapi/products/links"
    timestamp = str(int(_time.time() * 1000))

    message = REQUEST_METHOD + REQUEST_PATH + timestamp + access_key
    signature = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    authorization = f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={timestamp}, signature={signature}"

    try:
        resp = _req.get(
            f"https://api-gateway.coupang.com{REQUEST_PATH}",
            params={"coupangUrls": [actual_url]},
            headers={"Authorization": authorization},
            timeout=8
        )
        data = resp.json()
        
        # 디버깅: API 응답 전체 출력
        if data.get("rCode") != "0":
            print(f"[쿠팡 API 응답 오류] rCode: {data.get('rCode')}, rMessage: {data.get('rMessage')}")
            
        # 쿠팡 API 응답 구조: data 필드가 리스트인 경우 대응
        res_data = data.get("data")
        landing_url = None
        if isinstance(res_data, list) and len(res_data) > 0:
            landing_url = res_data[0].get("landingUrl")
        elif isinstance(res_data, dict):
            landing_url = res_data.get("landingUrl")
        
        if landing_url:
            return landing_url
    except Exception as e:
        print(f"[쿠팡 파트너스 API 에러] {e}")

    # 폴백: 원본 쿠팡 URL에 파트너스 추적 파라미터 직접 추가
    separator = '&' if '?' in actual_url else '?'
    return f"{actual_url}{separator}partnersCl={af_id}"


def convert_to_affiliate_link(url, shop_type):
    """
    원본 URL을 받아서 제휴(Affiliate) 링크로 변환합니다.
    실무에선 각 플랫폼의 API(예: 쿠팡 파트너스 도메인 생성 API, 알리 포털 API)를 
    호출하는 방식으로 구현됩니다. 
    지금은 파라미터를 추가하는 Mock 형태로 구현함.
    """
    if shop_type == 'coupang':
        return _generate_coupang_link(url)
        
    elif shop_type == 'aliexpress':
        # 알리 어필리에이트 URL 파라미터 조합 (간소화)
        separator = '&' if '?' in url else '?'
        return f"{url}{separator}aff_short_key={AFFILIATE_CONFIG['aliexpress']['tracking_id']}"
        
    elif shop_type == 'amazon':
        separator = '&' if '?' in url else '?'
        return f"{url}{separator}tag={AFFILIATE_CONFIG['amazon']['tag']}"
        
    elif shop_type == 'temu':
        separator = '&' if '?' in url else '?'
        return f"{url}{separator}invite_code={AFFILIATE_CONFIG['temu']['invite_code']}"
        
    return url # 변환할 수 없는 몰은 원본 링크 유지

# ── 해시태그 최적화 데이터 ────────────────────────────
HASHTAGS = {
    "common": ["#핫딜", "#꿀템", "#쇼핑", "#쇼핑스타그램", "#생활비절약", "#알뜰쇼핑"],
    "categories": {
        "electronics": ["#IT테크", "#전자기기", "#가전제품", "#애플", "#삼성", "#데스크테리어"],
        "fashion": ["#패션", "#오오티디", "#데일리룩", "#남친룩", "#여친룩", "#슈스타그램"],
        "food": ["#식품특가", "#먹스타그램", "#식객", "#자취생꿀템", "#냉장고파먹기"],
        "living": ["#인테리어", "#자취방꾸미기", "#생활용품", "#꿀팁", "#집꾸미기"]
    },
    "time_based": {
        "morning": ["#출근길", "#굿모닝", "#아침쇼핑"],
        "lunch": ["#점심시간", "#맛점", "#오늘의식단"],
        "night": ["#자기전", "#야식", "#새벽반"],
        "weekend": ["#주말쇼핑", "#나들이", "#집콕"]
    }
}

def get_optimized_hashtags(title, shop_type):
    """제목과 시간대를 분석해 최적의 해시태그 3~4개를 반환합니다."""
    selected = set()
    
    # 1. 쇼핑몰 기반 기본 태그
    shop_tags = {
        'coupang': '#쿠팡핫딜',
        'aliexpress': '#알리직구',
        'amazon': '#아마존대란',
        'temu': '#테무특가',
        'other': '#역대급특가'
    }
    selected.add(shop_tags.get(shop_type, shop_tags['other']))

    # 2. 카테고리 분석 (제목 키워드)
    keywords = {
        "electronics": ["노트북", "아이폰", "갤럭시", "키보드", "모니터", "패드", "맥북", "충전기"],
        "fashion": ["운동화", "나이키", "아디다스", "티셔츠", "셔츠", "슬랙스", "패딩", "청바지"],
        "food": ["식품", "생수", "커피", "간식", "음료", "즉석식품", "햇반", "닭가슴살"],
        "living": ["세제", "휴지", "물티슈", "청소기", "가구", "침구", "수건"]
    }
    for cat, kws in keywords.items():
        if any(kw in title for kw in kws):
            selected.update(random.sample(HASHTAGS["categories"][cat], 2))
            break
            
    # 3. 시간대/요일 기반 태그
    from datetime import datetime
    now = datetime.now()
    if now.weekday() >= 5: # 토, 일
        selected.add(random.choice(HASHTAGS["time_based"]["weekend"]))
    else:
        hour = now.hour
        if 7 <= hour < 10: selected.add(random.choice(HASHTAGS["time_based"]["morning"]))
        elif 11 <= hour < 14: selected.add(random.choice(HASHTAGS["time_based"]["lunch"]))
        elif 22 <= hour or hour < 2: selected.add(random.choice(HASHTAGS["time_based"]["night"]))

    # 부족하면 common에서 채움
    if len(selected) < 4:
        selected.update(random.sample(HASHTAGS["common"], 4 - len(selected)))

    # 결과물 정렬 (보기 좋게)
    res = list(selected)
    random.shuffle(res)
    return " ".join(res[:4]) # 최대 4개

_FALLBACK_INTROS = [
    "🚨 미쳤다 이거 당장 타!!!",
    "💸 하.. 내 지갑 또 털리네.",
    "🔥 이거 안 사면 흑우입니다;;",
    "🤯 이게 이 가격이라고?? 눈 비비고 다시 봄",
    "💀 지갑 묵념..",
    "⚡ 역대급 대란 발생.. 지금 당장 확인해야 함",
    "🛒 장바구니 넣기 전에 뇌정지 한번 옵니다",
    "🎯 이 가격 다시 없음. 이건 진짜임",
    "📢 전국민 탑승 시그널 발령합니다.",
    "🏃‍♂️💨 품절되기 전에 무지성 탑승 기기기기",
]

def generate_tweet_text(deal_info, converted_link, ai_desc="", shop_type=None):
    """
    봇 페르소나 (지갑털이범 / 호들갑 요정) 에 맞춰 트윗 본문을 생성합니다.
    ai_desc: (intro_line, desc_line) 튜플 또는 구버전 호환용 문자열
    shop_type: 이미 판별된 쇼핑몰 타입 (None이면 내부에서 판별)
    """
    title = deal_info.get('title', '핫딜 정보')
    price = deal_info.get('price', '')
    if shop_type is None:
        shop_type = identify_shop(deal_info.get('shop_url', ''), deal_info.get('store', ''))

    is_affiliate = shop_type == 'coupang'
    disclaimer_tag = "#광고 " if is_affiliate else ""

    # ai_desc가 튜플이면 새 형식 (intro, desc), 문자열이면 구버전 호환
    if isinstance(ai_desc, tuple):
        ai_intro, ai_body = ai_desc
    else:
        ai_intro, ai_body = None, ai_desc

    intro = ai_intro if ai_intro else random.choice(_FALLBACK_INTROS)
    desc_section = f"\n📝 {ai_body}\n" if ai_body else ""

    optimized_tags = get_optimized_hashtags(title, shop_type)

    tweet_text = (
        f"{disclaimer_tag}{intro}\n\n"
        f"[{shop_type.upper()}] {title}\n"
        f"💰 {price}"
        f"{desc_section}\n\n"
        f"👉 탑승링크:\n{converted_link}\n\n"
        f"{optimized_tags}"
    )

    # 쿠팡(제휴) 딜만 공정위 답글 달기, 비쿠팡은 None
    if is_affiliate:
        reply_text = "본 트윗의 링크를 통해 득템하시면, 저에게도 커피값 수준의 제휴 수수료가 떨어집니다! ☕\n덕분에 폰 요금 내면서 더 쩌는 핫딜 물어올게요 🫡 \n(수수료는 판매자가 냅니다, 여러분 결제액은 100% 동일!)"
    else:
        reply_text = None

    return tweet_text, reply_text

if __name__ == "__main__":
    # 포매터 테스트
    dummy_deal = {
        'title': "애플 맥북프로 M3 (역대가 갱신)",
        'price': "1,500,000원",
        'shop_url': "https://www.aliexpress.com/item/100500123.html?spm=a2g0o"
    }
    
    s_type = identify_shop(dummy_deal['shop_url'])
    c_link = convert_to_affiliate_link(dummy_deal['shop_url'], s_type)
    t_text, r_text = generate_tweet_text(dummy_deal, c_link)
    
    print("========== MAIN TWEET ==========")
    print(t_text)
    print("\n========== REPLY TWEET (공정위) ==========")
    print(r_text)
