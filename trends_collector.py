import time
import json
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from gnews import GNews
import openai
from pymongo import MongoClient
import schedule

# MongoDB 연결
MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGODB_URI)
db = client['trending_keywords']
collection = db['keywords']

# OpenAI API 설정
openai.api_key = os.environ.get('OPENAI_API_KEY', 'YOUR_API_KEY_HERE')

# 수집할 국가 설정 (AdSense 고단가 우선)
COUNTRIES = {
    # 최고 단가 (필수)
    'US': '미국',        # $10-15 CPM
    'CA': '캐나다',      # $8-12 CPM
    'AU': '호주',        # $7-11 CPM
    'GB': '영국',        # $8-13 CPM
    
    # 고단가 (추천)
    'DE': '독일',        # $6-10 CPM
    'FR': '프랑스',      # $5-9 CPM
    'NO': '노르웨이',    # $9-14 CPM
    'SE': '스웨덴',      # $8-12 CPM
    
    # 중단가
    'JP': '일본',        # $4-8 CPM
    'KR': '한국',        # $3-6 CPM
    'SG': '싱가포르',    # $6-10 CPM
}

# 7개 언어 설정
LANGUAGES = {
    'en': 'English',
    'ko': 'Korean',
    'ja': 'Japanese',
    'de': 'German',
    'fr': 'French',
    'no': 'Norwegian',
    'sv': 'Swedish'
}

# 국가별 Google Trends URL
TRENDS_URLS = {
    'US': 'https://trends.google.com/trending?geo=US',
    'CA': 'https://trends.google.ca/trending?geo=CA',
    'AU': 'https://trends.google.com.au/trending?geo=AU',
    'GB': 'https://trends.google.co.uk/trending?geo=GB',
    'DE': 'https://trends.google.de/trending?geo=DE',
    'FR': 'https://trends.google.fr/trending?geo=FR',
    'NO': 'https://trends.google.no/trending?geo=NO',
    'SE': 'https://trends.google.se/trending?geo=SE',
    'JP': 'https://trends.google.co.jp/trending?geo=JP',
    'KR': 'https://trends.google.co.kr/trending?geo=KR',
    'SG': 'https://trends.google.com.sg/trending?geo=SG'
}

def setup_driver():
    """Chrome 드라이버 설정"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # ChromeDriver 자동 설치 (오프라인 캐시 사용)
    try:
        service = Service(ChromeDriverManager().install())
    except Exception as e:
        print(f"  ⚠️ ChromeDriver 자동 설치 실패, 시스템 드라이버 사용: {e}")
        service = Service()
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_trending_keywords(country_code):
    """Selenium으로 Google Trends에서 실제 트렌드 키워드 수집"""
    driver = None
    try:
        print(f"  🌐 {country_code} 브라우저 시작 중...")
        driver = setup_driver()
        
        url = TRENDS_URLS.get(country_code)
        print(f"  📡 {url} 접속 중...")
        driver.get(url)
        
        print(f"  ⏳ 페이지 로딩 대기 중...")
        time.sleep(10)
        
        # 스크롤하여 콘텐츠 로드
        driver.execute_script("window.scrollTo(0, 1000);")
        time.sleep(3)
        
        # 디버깅: HTML 저장
        debug_dir = "debug_output"
        os.makedirs(debug_dir, exist_ok=True)
        
        html_file = f"{debug_dir}/{country_code}_trends.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print(f"  🐛 HTML 저장됨: {html_file}")
        
        # 스크린샷 저장
        screenshot_file = f"{debug_dir}/{country_code}_trends.png"
        driver.save_screenshot(screenshot_file)
        print(f"  📸 스크린샷 저장됨: {screenshot_file}")
        
        keywords = []
        
        # 다양한 셀렉터로 시도
        selectors = [
            "div.mZ3RIc",
            "div[class*='title']",
            "a[class*='title']",
            "div.feed-item-header",
            "div.summary-text a"
        ]
        
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    text = elem.text.strip()
                    if text and len(text) > 2 and text not in keywords:
                        keywords.append(text)
                        if len(keywords) >= 10:
                            break
                if len(keywords) >= 10:
                    break
            except:
                continue
        
        # 중복 제거 및 정리
        excluded_words = [
            'Trends', 'trending', '실시간 인기', '로그인', 'Login', 'Sign in',
            'location_on', 'menu', 'search', 'Google', '▾', '더보기', 'More',
            'Privacy', 'Terms', 'Help', 'Settings', 'Account', 'All categories'
        ]
        
        keywords = [
            kw for kw in keywords 
            if kw and len(kw) > 2 and kw not in excluded_words
        ]
        
        # 대소문자 구분 없이 중복 제거
        seen = {}
        unique_keywords = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen:
                seen[kw_lower] = True
                unique_keywords.append(kw)
        
        keywords = unique_keywords[:10]
        
        print(f"  ✅ {country_code} 트렌드 수집 완료: {len(keywords)}개")
        if keywords:
            print(f"  📝 수집된 키워드: {', '.join(keywords[:3])}...")
        
        return keywords
        
    except Exception as e:
        print(f"  ❌ {country_code} 트렌드 수집 실패: {e}")
        return []
        
    finally:
        if driver:
            driver.quit()

def get_news_for_keyword(keyword, country_code):
    """특정 키워드의 최신 뉴스 수집"""
    try:
        language_map = {
            'US': 'en', 'CA': 'en', 'AU': 'en', 'GB': 'en',
            'DE': 'de', 'FR': 'fr', 'NO': 'no', 'SE': 'sv',
            'JP': 'ja', 'KR': 'ko', 'SG': 'en'
        }
        
        language = language_map.get(country_code, 'en')
        google_news = GNews(language=language, country=country_code, max_results=5)
        news_items = google_news.get_news(keyword)
        
        if not news_items:
            return []
        
        news_summary = []
        for item in news_items[:5]:
            title = item.get('title', '')
            description = item.get('description', '')
            
            if title and len(title) > 10:
                news_summary.append({
                    'title': title,
                    'description': description,
                    'published': item.get('published date', '')
                })
        
        print(f"    📰 뉴스 {len(news_summary)}개 수집됨")
        return news_summary
        
    except Exception as e:
        print(f"    ⚠ {keyword} 뉴스 수집 실패: {e}")
        return []

def analyze_keyword_multilingual(keyword, news_data, country_name):
    """GPT-4로 7개 언어로 키워드 분석 (신규 함수)"""
    explanations = {}
    
    if not news_data:
        # 뉴스가 없을 경우 기본 메시지
        for lang_code in LANGUAGES.keys():
            explanations[lang_code] = f"Trending: {keyword}"
        return explanations
    
    # 뉴스 내용 추출
    news_contents = []
    for news in news_data:
        if news['title']:
            content = f"{news['title']}. {news['description']}"
            news_contents.append(content)
    
    news_text = "\n\n".join(news_contents)
    
    # 각 언어별로 설명 생성
    for lang_code, lang_name in LANGUAGES.items():
        try:
            print(f"    🌐 {lang_name} 설명 생성 중...")
            
            if lang_code == 'en':
                prompt = f"""You are a trending keyword analyst. Based on the news articles provided, explain why "{keyword}" is trending in {country_name}.

Related news:
{news_text}

Requirements:
1. Write a concise 2-3 sentence explanation in English
2. Focus ONLY on factual information from the news articles
3. Do NOT speculate or make assumptions
4. If no news context is provided, give a general but factual explanation
5. Write naturally and clearly

Provide ONLY the explanation text, no additional formatting."""

            elif lang_code == 'ko':
                prompt = f"""당신은 글로벌 트렌드 분석 전문가입니다.

키워드: "{keyword}"
국가: {country_name}

관련 뉴스:
{news_text}

위 뉴스 내용을 바탕으로, 이 키워드가 {country_name}에서 왜 인기 검색어가 되었는지 분석해주세요.

작성 규칙:
1. 구체적인 사건, 인물, 날짜, 수치만 작성
2. 추측이나 일반론 금지 - 오직 뉴스에 나온 사실만
3. 3-4문장으로 간결하게
4. 한국어로 작성

설명만 작성하세요."""

            elif lang_code == 'ja':
                prompt = f"""あなたはトレンドキーワードアナリストです。ニュース記事に基づいて、なぜ「{keyword}」が{country_name}でトレンドになっているかを説明してください。

関連ニュース:
{news_text}

要件:
1. 2-3文で簡潔に日本語で説明
2. ニュース記事の事実のみに焦点を当てる
3. 推測や仮定は禁止
4. 自然で明確に書く

説明のみを記述してください。"""

            elif lang_code == 'de':
                prompt = f"""Sie sind ein Trendschlüsselwort-Analyst. Basierend auf den bereitgestellten Nachrichtenartikeln erklären Sie, warum "{keyword}" in {country_name} im Trend liegt.

Verwandte Nachrichten:
{news_text}

Anforderungen:
1. Schreiben Sie eine prägnante 2-3-Satz-Erklärung auf Deutsch
2. Konzentrieren Sie sich NUR auf faktische Informationen aus den Nachrichtenartikeln
3. Spekulieren oder vermuten Sie NICHT
4. Schreiben Sie natürlich und klar

Geben Sie NUR den Erklärungstext an."""

            elif lang_code == 'fr':
                prompt = f"""Vous êtes un analyste de mots-clés tendance. Sur la base des articles de presse fournis, expliquez pourquoi "{keyword}" est tendance en {country_name}.

Actualités connexes:
{news_text}

Exigences:
1. Rédigez une explication concise de 2-3 phrases en français
2. Concentrez-vous UNIQUEMENT sur les informations factuelles des articles de presse
3. NE spéculez PAS et ne faites PAS d'hypothèses
4. Écrivez naturellement et clairement

Fournissez UNIQUEMENT le texte d'explication."""

            elif lang_code == 'no':
                prompt = f"""Du er en trendnøkkelordanalytiker. Basert på de gitte nyhetsartiklene, forklar hvorfor "{keyword}" er trending i {country_name}.

Relaterte nyheter:
{news_text}

Krav:
1. Skriv en kortfattet 2-3 setningsforklaring på norsk
2. Fokuser KUN på faktainformasjon fra nyhetsartiklene
3. IKKE spekuler eller gjør antagelser
4. Skriv naturlig og tydelig

Oppgi KUN forklaringsteksten."""

            elif lang_code == 'sv':
                prompt = f"""Du är en trendnyckelordsanalytiker. Baserat på de tillhandahållna nyhetsartiklarna, förklara varför "{keyword}" trendar i {country_name}.

Relaterade nyheter:
{news_text}

Krav:
1. Skriv en kortfattad 2-3 meningsförklaring på svenska
2. Fokusera ENDAST på faktainformation från nyhetsartiklarna
3. Spekulera INTE eller gör antaganden
4. Skriv naturligt och tydligt

Ange ENDAST förklaringstexten."""

            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": f"You are a professional news analyst. Always respond in {lang_name}."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=250,
                temperature=0.1
            )
            
            explanation = response.choices[0].message.content.strip()
            explanations[lang_code] = explanation
            print(f"    ✅ {lang_name} 설명 생성 완료")
            
            # API Rate Limit 방지
            time.sleep(1)
            
        except Exception as e:
            print(f"    ❌ {lang_name} 설명 생성 실패: {e}")
            explanations[lang_code] = f"Trending: {keyword}"
    
    return explanations

def save_to_mongodb(country_code, country_name, keywords_data):
    """MongoDB에 저장"""
    try:
        from datetime import timezone
        
        document = {
            'country_code': country_code,
            'country_name': country_name,
            'keywords': keywords_data,
            'updated_at': datetime.now(timezone.utc),  # UTC 시간으로 저장
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        collection.delete_many({'country_code': country_code})
        collection.insert_one(document)
        print(f"💾 {country_name} 데이터 저장 완료 (UTC: {document['updated_at']})\n")
        
    except Exception as e:
        print(f"❌ MongoDB 저장 실패: {e}\n")

def collect_trends_for_country(country_code, country_name):
    """국가별 트렌드 수집 및 분석 (다국어 지원)"""
    print(f"\n{'='*50}")
    print(f"🌍 {country_name} ({country_code}) 수집 시작...")
    print(f"{'='*50}")
    
    keywords = get_trending_keywords(country_code)
    
    if not keywords:
        print(f"❌ {country_name} 키워드 수집 실패\n")
        return
    
    keywords_data = []
    
    for rank, keyword in enumerate(keywords[:10], 1):
        print(f"\n[{rank}/10] 처리 중: {keyword}")
        
        news_data = get_news_for_keyword(keyword, country_code)
        time.sleep(1)
        
        # 7개 언어로 설명 생성
        explanations = analyze_keyword_multilingual(keyword, news_data, country_name)
        
        keywords_data.append({
            'rank': rank,
            'keyword': keyword,
            'explanations': explanations,  # 다국어 설명 객체
            'news_count': len(news_data)
        })
    
    save_to_mongodb(country_code, country_name, keywords_data)

def collect_all_trends():
    """모든 국가의 트렌드 수집"""
    print(f"\n🚀 트렌드 수집 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    for country_code, country_name in COUNTRIES.items():
        try:
            collect_trends_for_country(country_code, country_name)
            time.sleep(3)
        except Exception as e:
            print(f"❌ {country_name} 전체 수집 실패: {e}")
            continue
    
    print(f"\n✅ 모든 국가 수집 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

def main():
    """메인 실행 함수"""
    print("="*70)
    print("🔥 실시간 트렌드 수집 시스템 시작 (다국어 지원)")
    print("="*70)
    print(f"📅 수집 간격: 3시간마다")
    print(f"🌏 대상 국가: {', '.join(COUNTRIES.values())}")
    print(f"📊 키워드 수: 국가당 10개")
    print(f"🌐 지원 언어: 7개 (en, ko, ja, de, fr, no, sv)")
    print(f"📡 데이터 출처: Google Trends (Selenium)")
    print("="*70)
    
    # 즉시 1회 실행
    collect_all_trends()
    
    # 3시간마다 자동 실행
    schedule.every(3).hours.do(collect_all_trends)
    
    print("\n⏰ 스케줄러 시작 - 3시간마다 자동 수집")
    print("   (중지하려면 Ctrl+C를 누르세요)\n")
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 프로그램 종료")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")