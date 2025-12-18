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
    # chrome_options.add_argument('--headless')  # 일단 브라우저 창 보이도록 주석 처리
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
        # 시스템에 설치된 chromedriver 사용
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
        # 1. UI 요소 필터링 (버튼, 메뉴 등)
        excluded_words = [
            'Trends', 'trending', '실시간 인기', '로그인', 'Login', 'Sign in',
            'location_on', 'menu', 'search', 'Google', '▾', '더보기', 'More',
            'Privacy', 'Terms', 'Help', 'Settings', 'Account', 'All categories'
        ]
        
        keywords = [
            kw for kw in keywords 
            if kw and len(kw) > 2 and kw not in excluded_words
        ]
        
        # 2. 대소문자 구분 없이 중복 제거
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
    """특정 키워드의 최신 뉴스 수집 (개선 버전)"""
    try:
        # 언어별 설정 (검색 정확도 향상)
        language_map = {
            'US': 'en', 'CA': 'en', 'AU': 'en', 'GB': 'en',
            'DE': 'de', 'FR': 'fr', 'NO': 'no', 'SE': 'sv',
            'JP': 'ja', 'KR': 'ko', 'SG': 'en'
        }
        
        language = language_map.get(country_code, 'en')
        google_news = GNews(language=language, country=country_code, max_results=5)  # 5개로 증가
        news_items = google_news.get_news(keyword)
        
        if not news_items:
            return []
        
        news_summary = []
        for item in news_items[:5]:  # 5개로 증가
            title = item.get('title', '')
            description = item.get('description', '')
            
            # 의미 있는 뉴스만 선택
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

def analyze_keyword_with_gpt(keyword, news_data, country_name):
    """GPT-4로 키워드 분석 (프롬프트 개선 버전)"""
    try:
        if not news_data:
            return f"{keyword}에 대한 최신 뉴스를 찾을 수 없어 분석이 어렵습니다."
        
        # 뉴스 내용만 추출 (메타 정보 제거)
        news_contents = []
        for news in news_data:
            if news['title']:
                content = f"{news['title']}. {news['description']}"
                news_contents.append(content)
        
        news_text = "\n\n".join(news_contents)
        
        prompt = f"""당신은 글로벌 트렌드 분석 전문가입니다.

키워드: "{keyword}"
국가: {country_name}

관련 뉴스:
{news_text}

위 뉴스 내용을 바탕으로, 이 키워드가 {country_name}에서 왜 인기 검색어가 되었는지 분석해주세요.

작성 규칙:
1. "뉴스 1, 2, 3" 또는 "[뉴스 1]" 같은 메타 언급 절대 금지
2. 구체적인 사건, 인물, 날짜, 수치만 작성
3. 추측이나 일반론 금지 - 오직 뉴스에 나온 사실만
4. 3-4문장으로 간결하게
5. 한국어로 작성

좋은 예시:
"테일러 스위프트는 12월 15일 뉴욕에서 새 앨범 발매 기념 콘서트를 개최했습니다. 이번 콘서트는 5만 명의 관중을 동원하며 매진을 기록했습니다. 새 앨범은 빌보드 차트 1위를 차지했습니다."

절대 하지 말아야 할 예시:
"뉴스 1,2,3에 따르면 테일러 스위프트가 화제입니다."
"여러 뉴스에서 보도되고 있으며 팬들의 관심이 높습니다."
"""

        # 원래 작동하던 방식 그대로 사용
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "당신은 뉴스 기사를 분석하여 팩트만을 추출하는 전문가입니다. 메타 정보나 추측 없이 오직 구체적인 사실만 전달합니다."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.1
        )
        
        explanation = response.choices[0].message.content.strip()
        print(f"    ✅ GPT 분석 완료 ({len(explanation)}자)")
        return explanation
        
    except Exception as e:
        print(f"    ❌ GPT 분석 실패: {e}")
        if news_data:
            titles = " | ".join([n['title'][:50] for n in news_data[:2]])
            return f"{keyword}: {titles}... 등의 이유로 트렌딩 중입니다."
        return f"{keyword}는 {country_name}에서 현재 트렌딩 중인 인기 검색어입니다."

def save_to_mongodb(country_code, country_name, keywords_data):
    """MongoDB에 저장"""
    try:
        document = {
            'country_code': country_code,
            'country_name': country_name,
            'keywords': keywords_data,
            'updated_at': datetime.now(),
            'timestamp': datetime.now().isoformat()
        }
        
        collection.delete_many({'country_code': country_code})
        collection.insert_one(document)
        print(f"💾 {country_name} 데이터 저장 완료\n")
        
    except Exception as e:
        print(f"❌ MongoDB 저장 실패: {e}\n")

def collect_trends_for_country(country_code, country_name):
    """국가별 트렌드 수집 및 분석"""
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
        
        explanation = analyze_keyword_with_gpt(keyword, news_data, country_name)
        time.sleep(1)
        
        keywords_data.append({
            'rank': rank,
            'keyword': keyword,
            'explanation': explanation,
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
    print("🔥 실시간 트렌드 수집 시스템 시작 (Selenium v2)")
    print("="*70)
    print(f"📅 수집 간격: 3시간마다")
    print(f"🌏 대상 국가: {', '.join(COUNTRIES.values())}")
    print(f"📊 키워드 수: 국가당 10개")
    print(f"📡 데이터 출처: Google Trends (Selenium)")
    print(f"🐛 디버그: HTML/PNG 파일 자동 저장")
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