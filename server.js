const express = require('express');
const { MongoClient } = require('mongodb');
const cors = require('cors');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// MongoDB 연결
const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/';
const client = new MongoClient(MONGODB_URI);

let db;
let collection;
let isConnected = false;

// MongoDB 연결 함수 (Vercel용 - 재사용 가능하게)
async function connectDB() {
    if (isConnected) {
        return;
    }
    
    try {
        await client.connect();
        db = client.db('trending_keywords');
        collection = db.collection('keywords');
        isConnected = true;
        console.log('✅ MongoDB 연결 성공');
    } catch (error) {
        console.error('❌ MongoDB 연결 실패:', error);
        throw error;
    }
}

// 미들웨어
app.use(cors());
app.use(express.json());

// 정적 파일 캐시 설정
app.use(express.static('public', {
    maxAge: '1h', // 1시간 캐시
    etag: true,
    lastModified: true
}));

// API: 모든 국가의 트렌드 가져오기
app.get('/api/trends', async (req, res) => {
    try {
        await connectDB(); // Vercel용 - 매번 연결 확인
        
        const trends = await collection.find({}).toArray();
        
        // 국가별로 정렬 (애드센스 고단가 순서)
        const countryOrder = ['US', 'CA', 'AU', 'GB', 'DE', 'FR', 'NO', 'SE', 'JP', 'KR', 'SG'];
        trends.sort((a, b) => {
            return countryOrder.indexOf(a.country_code) - countryOrder.indexOf(b.country_code);
        });
        
        console.log(`📊 ${trends.length}개 국가 데이터 전송`);
        
        res.json({
            success: true,
            data: trends,
            count: trends.length
        });
    } catch (error) {
        console.error('❌ API 오류:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// API: 특정 국가의 트렌드 가져오기
app.get('/api/trends/:country', async (req, res) => {
    try {
        await connectDB(); // Vercel용 - 매번 연결 확인
        
        const country = req.params.country.toUpperCase();
        const trend = await collection.findOne({ country_code: country });
        
        if (!trend) {
            return res.status(404).json({
                success: false,
                error: '해당 국가 데이터를 찾을 수 없습니다.'
            });
        }
        
        console.log(`📊 ${country} 데이터 전송`);
        
        res.json({
            success: true,
            data: trend
        });
    } catch (error) {
        console.error('❌ API 오류:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// 루트 경로 - 브라우저 언어로 리다이렉트
app.get('/', (req, res) => {
    const acceptLang = req.headers['accept-language'];
    let lang = 'en';
    
    if (acceptLang) {
        const browserLang = acceptLang.split(',')[0].split('-')[0];
        if (['de', 'fr', 'ja', 'ko', 'no', 'sv'].includes(browserLang)) {
            lang = browserLang;
        }
    }
    
    res.redirect(`/${lang}`);
});

// 언어별 루트 (/en, /de, /ja, /ko, /fr, /no, /sv)
app.get('/:lang(en|de|fr|ja|ko|no|sv)', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// 언어 + 국가 (/en/us, /de/de, /ja/jp 등)
app.get('/:lang(en|de|fr|ja|ko|no|sv)/:country(us|ca|au|gb|de|fr|no|se|jp|kr|sg)', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// 서버 시작 (로컬) 또는 export (Vercel)
if (process.env.NODE_ENV !== 'production') {
    // 로컬 개발 환경
    connectDB().then(() => {
        app.listen(PORT, () => {
            console.log('='.repeat(50));
            console.log('🚀 트렌드 웹사이트 서버 시작!');
            console.log(`📡 웹사이트: http://localhost:${PORT}`);
            console.log(`📊 API: http://localhost:${PORT}/api/trends`);
            console.log(`🌍 다국어: http://localhost:${PORT}/en (en/de/fr/ja/ko/no/sv)`);
            console.log('='.repeat(50));
        });
    });
} else {
    // Vercel 배포 환경
    connectDB();
}

// Vercel용 export
module.exports = app;