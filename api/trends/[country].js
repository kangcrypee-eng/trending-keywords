const { MongoClient } = require('mongodb');

const MONGODB_URI = process.env.MONGODB_URI;
const client = new MongoClient(MONGODB_URI);

let cachedDb = null;

async function connectDB() {
    if (cachedDb) {
        return cachedDb;
    }
    
    await client.connect();
    const db = client.db('trending_keywords');
    cachedDb = db;
    return db;
}

module.exports = async (req, res) => {
    // CORS 헤더
    res.setHeader('Access-Control-Allow-Credentials', true);
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    if (req.method === 'OPTIONS') {
        res.status(200).end();
        return;
    }
    
    try {
        const { country } = req.query;
        const countryCode = country.toUpperCase();
        
        const db = await connectDB();
        const collection = db.collection('keywords');
        
        const trend = await collection.findOne({ country_code: countryCode });
        
        if (!trend) {
            return res.status(404).json({
                success: false,
                error: '해당 국가 데이터를 찾을 수 없습니다.'
            });
        }
        
        res.status(200).json({
            success: true,
            data: trend
        });
        
    } catch (error) {
        console.error('API 오류:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};
