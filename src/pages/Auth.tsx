import React, { useState } from 'react';

interface AuthProps {
    onLogin: (userData: any) => void;
}

const Auth: React.FC<AuthProps> = ({ onLogin }) => {
    const [isLogin, setIsLogin] = useState(true);
    const [formData, setFormData] = useState({
        name: '',
        phone: '',
        password: '', // 비밀번호 추가
        dong: '',
        ho: '',
        carPlate: '',
    });

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value } = e.target;
        if (name === 'phone') {
            const cleaned = value.replace(/\D/g, '').slice(0, 11);
            let formatted = cleaned;
            if (cleaned.length <= 3) {
                formatted = cleaned;
            } else if (cleaned.length <= 7) {
                formatted = `${cleaned.slice(0, 3)}-${cleaned.slice(3)}`;
            } else {
                formatted = `${cleaned.slice(0, 3)}-${cleaned.slice(3, 7)}-${cleaned.slice(7)}`;
            }
            setFormData({ ...formData, [name]: formatted });
        } else if (name === 'carPlate') {
            setFormData({ ...formData, [name]: value.toUpperCase().replace(/\s/g, '') });
        } else {
            setFormData({ ...formData, [name]: value });
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            if (isLogin) {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        phone: formData.phone,
                        password: formData.password
                    }),
                });

                if (response.ok) {
                    const userData = await response.json();
                    onLogin(userData);
                } else {
                    const error = await response.json();
                    alert(error.error || '로그인에 실패했습니다.');
                }
            } else {
                // 실제 회원가입 API 호출
                const unitNumber = `${formData.dong}-${formData.ho}`;
                const response = await fetch('/api/signup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: formData.name,
                        phone: formData.phone,
                        password: formData.password,
                        unitNumber,
                        carPlate: formData.carPlate
                    }),
                });

                if (response.ok) {
                    alert('회원가입이 완료되었습니다! 로그인해주세요.');
                    setIsLogin(true); // 로그인 화면으로 전환
                } else {
                    const error = await response.json();
                    alert(error.error || '회원가입에 실패했습니다.');
                }
            }
        } catch (error) {
            console.error('인증 오류:', error);
            alert('서버와 통신 중 오류가 발생했습니다.');
        }
    };

    return (
        <div className="auth-container page-transition" style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: '100vh',
            padding: '20px'
        }}>
            <div className="card glass-card" style={{ width: '100%', maxWidth: '440px', padding: '48px' }}>
                <div style={{ textAlign: 'center', marginBottom: '40px' }}>
                    <div style={{ fontWeight: '800', fontSize: '1.25rem', color: 'var(--accent-blue)', marginBottom: '8px', letterSpacing: '0.1em' }}>
                        SMART PARKING
                    </div>
                    <h2 style={{ fontSize: '1.75rem', marginBottom: '8px' }}>
                        {isLogin ? 'Welcome Back' : 'Create Account'}
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                        {isLogin ? '로그인하여 주차 서비스를 이용하세요.' : '신규 입주자 정보를 등록하세요.'}
                    </p>
                </div>

                <form onSubmit={handleSubmit}>
                    {!isLogin && (
                        <>
                            <label>Name</label>
                            <input
                                type="text"
                                name="name"
                                placeholder="이름을 입력하세요"
                                required
                                value={formData.name}
                                onChange={handleChange}
                            />
                        </>
                    )}

                    <label>Phone Number</label>
                    <input
                        type="tel"
                        name="phone"
                        placeholder="010-0000-0000"
                        required
                        value={formData.phone}
                        onChange={handleChange}
                    />

                    <label>Password</label>
                    <input
                        type="password"
                        name="password"
                        placeholder="비밀번호를 입력하세요"
                        required
                        value={formData.password}
                        onChange={handleChange}
                    />

                    {!isLogin && (
                        <>
                            <div style={{ display: 'flex', gap: '16px' }}>
                                <div style={{ flex: 1 }}>
                                    <label>Building</label>
                                    <input
                                        type="text"
                                        name="dong"
                                        placeholder="동 (예: 101)"
                                        required
                                        value={formData.dong}
                                        onChange={handleChange}
                                    />
                                </div>
                                <div style={{ flex: 1 }}>
                                    <label>Unit</label>
                                    <input
                                        type="text"
                                        name="ho"
                                        placeholder="호 (예: 101)"
                                        required
                                        value={formData.ho}
                                        onChange={handleChange}
                                    />
                                </div>
                            </div>
                            <label>Vehicle Plate</label>
                            <input
                                type="text"
                                name="carPlate"
                                placeholder="차량 번호 (예: 12가1234)"
                                required
                                value={formData.carPlate}
                                onChange={handleChange}
                            />
                        </>
                    )}

                    <button type="submit" className="primary" style={{ width: '100%', marginTop: '12px', height: '50px' }}>
                        {isLogin ? 'LOG IN' : 'SIGN UP'}
                    </button>
                </form>

                <div style={{ textAlign: 'center', marginTop: '32px', borderTop: '1px solid var(--border-color)', paddingTop: '24px' }}>
                    {isLogin ? (
                        <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                            계정이 없으신가요?{' '}
                            <span
                                style={{ color: 'var(--accent-blue)', cursor: 'pointer', fontWeight: '700' }}
                                onClick={() => setIsLogin(false)}
                            >
                                회원가입
                            </span>
                        </p>
                    ) : (
                        <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                            이미 계정이 있으신가요?{' '}
                            <span
                                style={{ color: 'var(--accent-blue)', cursor: 'pointer', fontWeight: '700' }}
                                onClick={() => setIsLogin(true)}
                            >
                                로그인
                            </span>
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Auth;
