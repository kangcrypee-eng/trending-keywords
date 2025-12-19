const { MongoClient } = require('mongodb');

let cachedClient = null;
let cachedDb = null;

async function connectToDatabase() {
    if (cachedClient && cachedDb) {
        return { client: cachedClient, db: cachedDb };
    }

    // 옵션 제거 - 최신 MongoDB 드라이버는 자동 처리
    const client = await MongoClient.connect(process.env.MONGODB_URI);

    const db = client.db('trending_keywords');

    cachedClient = client;
    cachedDb = db;

    return { client, db };
}

module.exports = async (req, res) => {
    // CORS 설정
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    if (req.method !== 'GET') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        // 환경변수 체크
        if (!process.env.MONGODB_URI) {
            return res.status(500).json({
                success: false,
                error: 'MONGODB_URI not configured'
            });
        }

        // MongoDB 연결
        const { db } = await connectToDatabase();
        const collection = db.collection('keywords');

        // 데이터 조회
        const trends = await collection
            .find({})
            .sort({ updated_at: -1 })
            .toArray();

        // 데이터가 없을 경우
        if (!trends || trends.length === 0) {
            return res.status(200).json({
                success: true,
                data: [],
                message: 'No trends data available yet. Please run trends_collector.py first.'
            });
        }

        // 데이터 포맷팅
        const formattedData = trends.map(trend => ({
            country_code: trend.country_code,
            country_name: trend.country_name,
            updated_at: trend.updated_at,
            keywords: (trend.keywords || []).map(kw => ({
                rank: kw.rank,
                keyword: kw.keyword,
                explanations: kw.explanations || {},
                news_count: kw.news_count || 0
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
            error: error.message,
            debug: {
                hasMongoUri: !!process.env.MONGODB_URI,
                errorName: error.name
            }
        });
    }
};