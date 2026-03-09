# 🚀 Termux 핫딜 봇 (Hot Deal Bot)

안드로이드 Termux 환경에서 24시간 구동되는 자동 핫딜 알림 봇입니다. 
알구몬, 어미새, 뽐뿌 등 주요 커뮤니티의 핫딜을 수집하여 트위터(X)와 텔레그램으로 자동 발행합니다.

## ✨ 주요 기능
- **멀티 채널 수집:** 알구몬, 어미새, 뽐뿌 핫딜 실시간 크롤링
- **AI 설명 생성:** Google Gemini API를 사용한 제품 설명 및 이모지 자동 생성
- **제휴 링크 변환:** 쿠팡 파트너스 등 다양한 제휴 마케팅 링크 자동 변환
- **24시간 자동화:** Termux 환경 최적화 및 스케줄링 (15분 주기)

## 🛠️ 시작하기 (Quick Start)
1. 저장소 클론: `git clone https://github.com/smartcall1/termux_add.git`
2. 패키지 설치: `pip install -r requirements.txt`
3. 설정 파일 생성: `.env.template` 파일을 복사하여 `.env`를 만들고 API 키를 입력하세요.
4. 실행: `python main.py`

## ⚖️ 라이선스
MIT License

---
*본 프로젝트는 개인적인 학습 및 자동화 목적으로 제작되었습니다.*
