import time
import json
import os
from datetime import datetime, timezone
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from gnews import GNews
from openai import OpenAI
from pymongo import MongoClient


# MongoDB 연결
MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGODB_URI)
db = client['trending_keywords']
collection = db['keywords']

# OpenAI API 설정
openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY', 'YOUR_API_KEY_HERE'))

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
    """GPT로 7개 언어 동시 생성 (1회 API 호출로 최적화)"""
    explanations = {}
    
    # 뉴스 데이터 검증
    if not news_data or len(news_data) == 0:
        print(f"    ⚠️ 뉴스 데이터 없음, 기본 메시지 사용")
        for lang_code in LANGUAGES.keys():
            explanations[lang_code] = f"Trending: {keyword}"
        return explanations
    
    print(f"    📊 뉴스 {len(news_data)}개로 7개 언어 동시 분석")
    
    # 뉴스 내용 추출
    news_contents = []
    for news in news_data:
        if news['title']:
            content = f"{news['title']}. {news['description']}"
            news_contents.append(content)
    
    news_text = "\n\n".join(news_contents)
    
    # 🚀 1번의 API 호출로 7개 언어 모두 생성
    try:
        print(f"    🌐 7개 언어 동시 생성 중...")
        
        prompt = f"""You are a professional news analyst. Generate explanations for why "{keyword}" is trending in {country_name} in ALL 7 languages simultaneously.

Related news:
{news_text}

Generate EXACTLY in this format (no extra text):

ENGLISH:
[2-3 sentence explanation in English based on the news]

KOREAN:
[3-4문장 한국어 설명 - 뉴스 사실만 포함]

JAPANESE:
[2-3文の日本語説明]

GERMAN:
[2-3 Sätze auf Deutsch]

FRENCH:
[2-3 phrases en français]

NORWEGIAN:
[2-3 setninger på norsk]

SWEDISH:
[2-3 meningar på svenska]

Rules:
- Focus ONLY on facts from the news
- No speculation or assumptions
- Concise and clear
- Each language section must start with the language name in ALL CAPS followed by colon"""

        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a multilingual news analyst. Generate explanations in all requested languages."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.1
        )
        
        if response and response.choices and len(response.choices) > 0:
            full_text = response.choices[0].message.content.strip()
            
            # 언어별로 파싱
            language_markers = {
                'en': 'ENGLISH:',
                'ko': 'KOREAN:',
                'ja': 'JAPANESE:',
                'de': 'GERMAN:',
                'fr': 'FRENCH:',
                'no': 'NORWEGIAN:',
                'sv': 'SWEDISH:'
            }
            
            for lang_code, marker in language_markers.items():
                try:
                    start_idx = full_text.find(marker)
                    if start_idx == -1:
                        explanations[lang_code] = f"Trending: {keyword}"
                        continue
                    
                    # 다음 언어 마커 찾기
                    next_markers = [m for m in language_markers.values() if m != marker]
                    end_idx = len(full_text)
                    for next_marker in next_markers:
                        next_idx = full_text.find(next_marker, start_idx + len(marker))
                        if next_idx != -1 and next_idx < end_idx:
                            end_idx = next_idx
                    
                    # 추출 및 정리
                    explanation = full_text[start_idx + len(marker):end_idx].strip()
                    if explanation and len(explanation) > 10:
                        explanations[lang_code] = explanation
                    else:
                        explanations[lang_code] = f"Trending: {keyword}"
                except:
                    explanations[lang_code] = f"Trending: {keyword}"
            
            print(f"    ✅ 7개 언어 동시 생성 완료 (1회 API 호출)")
        else:
            print(f"    ⚠️ API 응답 오류")
            for lang_code in LANGUAGES.keys():
                explanations[lang_code] = f"Trending: {keyword}"
                
    except Exception as e:
        print(f"    ❌ API 호출 실패: {type(e).__name__}: {str(e)}")
        for lang_code in LANGUAGES.keys():
            explanations[lang_code] = f"Trending: {keyword}"
        
        # 상세 에러 로깅
        import traceback
        print(f"    🐛 상세 에러: {traceback.format_exc()}")
    
    return explanations

def save_to_mongodb(country_code, country_name, keywords_data):
    """MongoDB에 저장"""
    try:
        document = {
            'country_code': country_code,
            'country_name': country_name,
            'keywords': keywords_data,
            'updated_at': datetime.now(timezone.utc),
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
            'explanations': explanations,
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
    """메인 실행 함수 - GitHub Actions용"""
    print("="*70)
    print("🔥 실시간 트렌드 수집 시스템 시작 (다국어 지원)")
    print("="*70)
    print(f"🌏 대상 국가: {', '.join(COUNTRIES.values())}")
    print(f"📊 키워드 수: 국가당 10개")
    print(f"🌐 지원 언어: 7개 (en, ko, ja, de, fr, no, sv)")
    print(f"📡 데이터 출처: Google Trends (Selenium)")
    print("="*70)
    
    # GitHub Actions용: 1회만 실행하고 종료
    collect_all_trends()
    
    print("\n✅ 수집 완료!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 프로그램 종료")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        raise  # GitHub Actions에 에러 전달