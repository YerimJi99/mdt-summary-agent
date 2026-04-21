# MDT 다학제 회의 자동 요약 AI Agent

STT 전사 텍스트 + EMR 맥락 → Gemini 2.5 Flash → 구조화 요약 → 의료진 검수 → Ground Truth 축적

## 실행 방법

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 실행
streamlit run app.py
```

브라우저에서 http://localhost:8501 접속

## 배포 방법 (Streamlit Community Cloud — 무료)

1. GitHub에 이 폴더를 push
2. https://share.streamlit.io 에서 앱 연결
3. Gemini API 키는 Settings → Secrets에서 GEMINI_API_KEY로 등록

## 사용 흐름

1. 사이드바에 Gemini API 키 입력
2. [입력 & EMR] 탭: 전사 텍스트 붙여넣기 + EMR 데이터 입력
3. "AI 구조화 요약 생성" 버튼 클릭
4. [요약 검수] 탭: 섹션별 내용 확인 및 수정
5. 만족도 평가 후 "승인 및 Ground Truth 저장"
6. [현황 & 이력] 탭: 축적 현황 및 전체 데이터 다운로드
