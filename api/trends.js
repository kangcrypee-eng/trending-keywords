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
        const db = await connectDB();
        const collection = db.collection('keywords');
        
        const trends = await collection.find({}).toArray();
        
        // 국가별로 정렬
        const countryOrder = ['US', 'CA', 'AU', 'GB', 'DE', 'FR', 'NO', 'SE', 'JP', 'KR', 'SG'];
        trends.sort((a, b) => {
            return countryOrder.indexOf(a.country_code) - countryOrder.indexOf(b.country_code);
        });
        
        res.status(200).json({
            success: true,
            data: trends,
            count: trends.length
        });
        
    } catch (error) {
        console.error('API 오류:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};