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

def get_ai_description(title, price):
    """
    Gemini API를 사용하여 제품명 기반으로 매력적인 설명 피드를 생성합니다.
    """
    if not model:
        return ""
        
    prompt = f"""
    너는 인스타그램/트위터에서 유명한 한국의 '핫딜 지갑털이범'이야. 
    사용자들이 제품을 사고 싶게 만드는 짧고 강렬한 한 줄 설명을 작성해줘.
    
    [규칙]
    1. 제품명과 가격 정보를 바탕으로 이 제품의 핵심 장점이나 왜 지금 사야 하는지 강조해.
    2. 구어체(~함, ~임, ~임;;)를 사용하고 이모지를 1~2개 섞어줘.
    3. 길이는 공백 포함 40자 이내로 아주 짧게 작성해.
    4. 광고성 멘트보다는 진심으로 추천하는 느낌을 줘.
    
    제품명: {title}
    가격: {price}
    
    출력:
    """
    try:
        response = model.generate_content(prompt)
        return response.text.strip().replace('"', '')
    except Exception as e:
        print(f"Gemini API 에러: {e}")
        return ""

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
            params={"coupangUrls": actual_url},
            headers={"Authorization": authorization},
            timeout=8
        )
        data = resp.json()
        landing_url = data.get("data", {}).get("landingUrl")
        if landing_url:
            return landing_url
    except Exception as e:
        print(f"[쿠팡 파트너스 API 에러] {e}")

    # 폴백: af_id 기반 간이 링크
    return f"https://link.coupang.com/a/{af_id}?url={actual_url}"


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

def generate_tweet_text(deal_info, converted_link, ai_desc="", shop_type=None):
    """
    봇 페르소나 (지갑털이범 / 호들갑 요정) 에 맞춰 트윗 본문을 생성합니다.
    ai_desc: 이미 생성된 Gemini 설명 (main.py에서 전달, 중복 호출 방지)
    shop_type: 이미 판별된 쇼핑몰 타입 (None이면 내부에서 판별)
    """
    title = deal_info.get('title', '핫딜 정보')
    price = deal_info.get('price', '')
    if shop_type is None:
        shop_type = identify_shop(deal_info.get('shop_url', ''), deal_info.get('store', ''))

    is_affiliate = shop_type == 'coupang'
    disclaimer_tag = "#광고 " if is_affiliate else ""

    intro_candidates = [
        "🚨 미쳤다 이거 당장 타!!!",
        "💸 하.. 내 지갑 또 털리네.",
        "🔥 잠시만요 스탑!! 이거 안 사면 흑우입니다;;",
        "🏃‍♂️💨 품절되기 전에 무지성 탑승 기기기기",
        "🤯 이게 이 가격이라고?? 눈 비비고 다시 봄",
        "📢 전국민 탑승 시그널 발령합니다.",
        "💀 지갑 묵념..",
        "⚡ 역대급 대란 발생.. 지금 당장 확인해야 함",
        "🛒 장바구니에 넣기 전에 뇌정지 한번 옵니다",
        "🎯 이 가격 다시 없음. 이건 진짜임",
    ]
    intro = random.choice(intro_candidates)

    desc_section = f"\n📝 {ai_desc}\n" if ai_desc else ""

    shop_tags = {
        'coupang': '#쿠팡핫딜',
        'aliexpress': '#알리직구',
        'amazon': '#아마존대란',
        'temu': '#테무특가',
        'other': '#역대급특가'
    }
    shop_tag = shop_tags.get(shop_type, shop_tags['other'])

    tweet_text = f"{disclaimer_tag}{intro}\n\n[{shop_type.upper()}] {title}\n💰 {price}{desc_section}\n\n👉 탑승링크:\n{converted_link}\n\n{shop_tag}"

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
