// Vercel Serverless Function for sending contact form emails
// Uses nodemailer to send emails via Gmail SMTP

const nodemailer = require('nodemailer');

module.exports = async (req, res) => {
    // CORS 설정
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    // OPTIONS 요청 처리
    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    // POST 요청만 허용
    if (req.method !== 'POST') {
        return res.status(405).json({
            success: false,
            error: 'Method not allowed'
        });
    }

    try {
        const { name, email, subject, message } = req.body;

        // 입력 검증
        if (!name || !email || !subject || !message) {
            return res.status(400).json({
                success: false,
                error: 'All fields are required'
            });
        }

        // 이메일 형식 검증
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            return res.status(400).json({
                success: false,
                error: 'Invalid email format'
            });
        }

        // Gmail SMTP를 사용한 이메일 전송 설정
        // 환경변수에 Gmail 계정 정보가 필요합니다
        const transporter = nodemailer.createTransport({
            service: 'gmail',
            auth: {
                user: process.env.GMAIL_USER || 'your-email@gmail.com',
                pass: process.env.GMAIL_APP_PASSWORD || 'your-app-password'
            }
        });

        // 이메일 내용 구성
        const mailOptions = {
            from: process.env.GMAIL_USER,
            to: 'kang.crypee@gmail.com',
            subject: `[RealtimeKeyword Contact] ${subject}`,
            html: `
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #667eea;">New Contact Form Submission</h2>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <p><strong>Name:</strong> ${name}</p>
                        <p><strong>Email:</strong> ${email}</p>
                        <p><strong>Subject:</strong> ${subject}</p>
                    </div>
                    
                    <div style="background: white; padding: 20px; border: 1px solid #e9ecef; border-radius: 8px;">
                        <h3 style="color: #2d3748; margin-top: 0;">Message:</h3>
                        <p style="white-space: pre-wrap; line-height: 1.6;">${message}</p>
                    </div>
                    
                    <p style="color: #636e72; font-size: 0.9em; margin-top: 20px;">
                        This email was sent from the RealtimeKeyword contact form.
                    </p>
                </div>
            `,
            replyTo: email
        };

        // 이메일 전송
        await transporter.sendMail(mailOptions);

        return res.status(200).json({
            success: true,
            message: 'Email sent successfully'
        });

    } catch (error) {
        console.error('Contact form error:', error);
        return res.status(500).json({
            success: false,
            error: 'Failed to send email',
            message: error.message
        });
    }
};