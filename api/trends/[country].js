const { MongoClient } = require('mongodb');

const MONGODB_URI = process.env.MONGODB_URI;

let cachedClient = null;
let cachedDb = null;

async function connectToDatabase() {
    if (cachedClient && cachedDb) {
        return { client: cachedClient, db: cachedDb };
    }

    const client = await MongoClient.connect(MONGODB_URI, {
        useNewUrlParser: true,
        useUnifiedTopology: true,
    });

    const db = client.db('trending_keywords');

    cachedClient = client;
    cachedDb = db;

    return { client, db };
}

module.exports = async (req, res) => {
    // CORS 헤더 설정
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    // OPTIONS 요청 처리
    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    // GET 요청만 허용
    if (req.method !== 'GET') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        // MongoDB 연결
        const { db } = await connectToDatabase();
        const collection = db.collection('trends');

        // 모든 국가의 트렌드 데이터 가져오기
        const trends = await collection
            .find({})
            .sort({ updated_at: -1 })
            .toArray();

        if (!trends || trends.length === 0) {
            return res.status(200).json({
                success: true,
                data: [],
                message: 'No trends data available yet'
            });
        }

        // 응답 데이터 포맷팅
        const formattedData = trends.map(trend => ({
            country_code: trend.country_code,
            country_name: trend.country_name,
            updated_at: trend.updated_at,
            keywords: trend.keywords.map(kw => ({
                rank: kw.rank,
                keyword: kw.keyword,
                explanations: kw.explanations, // 다국어 설명 객체
                news_articles: kw.news_articles || []
            }))
        }));

        return res.status(200).json({
            success: true,
            data: formattedData,
            count: formattedData.length,
            last_updated: trends[0].updated_at
        });

    } catch (error) {
        console.error('API Error:', error);
        return res.status(500).json({
            success: false,
            error: 'Internal server error',
            message: error.message
        });
    }
};