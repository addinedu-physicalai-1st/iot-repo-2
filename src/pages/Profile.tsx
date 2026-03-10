import React, { useState } from 'react';

interface ProfileProps {
    user: any;
    onUpdateUser: (userData: any) => void;
}

const Profile: React.FC<ProfileProps> = ({ user, onUpdateUser }) => {
    const [formData, setFormData] = useState({
        name: user.name,
        phone: user.phone,
        currentPassword: '',
        newPassword: '',
        confirmPassword: ''
    });
    const [status, setStatus] = useState({ type: '', message: '' });

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value } = e.target;
        setFormData({ ...formData, [name]: value });
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setStatus({ type: '', message: '' });

        if (formData.newPassword && formData.newPassword !== formData.confirmPassword) {
            setStatus({ type: 'error', message: '새 비밀번호가 일치하지 않습니다.' });
            return;
        }

        try {
            const response = await fetch('/api/profile/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    phone: user.phone,
                    name: formData.name,
                    currentPassword: formData.currentPassword,
                    newPassword: formData.newPassword
                }),
            });

            const result = await response.json();

            if (response.ok) {
                setStatus({ type: 'success', message: '정보가 성공적으로 업데이트되었습니다.' });
                onUpdateUser({ ...user, name: formData.name });
                setFormData({ ...formData, currentPassword: '', newPassword: '', confirmPassword: '' });
            } else {
                setStatus({ type: 'error', message: result.error || '업데이트에 실패했습니다.' });
            }
        } catch (error) {
            console.error('프로필 업데이트 오류:', error);
            setStatus({ type: 'error', message: '서버와 통신 중 오류가 발생했습니다.' });
        }
    };

    return (
        <div className="page-transition">
            <div style={{ marginBottom: '40px' }}>
                <h1>개인 정보 설정</h1>
                <p style={{ color: 'var(--text-secondary)' }}>이름 및 비밀번호를 관리할 수 있습니다.</p>
            </div>

            <div className="card glass-card" style={{ maxWidth: '600px', margin: '0 auto' }}>
                <form onSubmit={handleSubmit}>
                    <div style={{ marginBottom: '32px' }}>
                        <h3 style={{ marginBottom: '16px' }}>기본 정보</h3>
                        <label>성함</label>
                        <input
                            type="text"
                            name="name"
                            value={formData.name}
                            onChange={handleChange}
                            required
                        />
                        <label>연락처 (변경 불가)</label>
                        <input
                            type="text"
                            value={formData.phone}
                            disabled
                            style={{ background: 'var(--light-gray)', cursor: 'not-allowed' }}
                        />
                        <label>거주지 (변경 불가)</label>
                        <input
                            type="text"
                            value={`${user.unitNumber}호`}
                            disabled
                            style={{ background: 'var(--light-gray)', cursor: 'not-allowed' }}
                        />
                    </div>

                    <div style={{ marginBottom: '32px', paddingTop: '24px', borderTop: '1px solid var(--border-color)' }}>
                        <h3 style={{ marginBottom: '16px' }}>비밀번호 변경</h3>
                        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '20px' }}>
                            보안을 위해 정보를 변경하려면 현재 비밀번호를 입력해야 합니다.
                        </p>

                        <label>현재 비밀번호</label>
                        <input
                            type="password"
                            name="currentPassword"
                            placeholder="현재 비밀번호를 입력하세요"
                            value={formData.currentPassword}
                            onChange={handleChange}
                            required
                        />

                        <label>새 비밀번호 (변경할 경우만 입력)</label>
                        <input
                            type="password"
                            name="newPassword"
                            placeholder="새 비밀번호를 입력하세요"
                            value={formData.newPassword}
                            onChange={handleChange}
                        />

                        <label>새 비밀번호 확인</label>
                        <input
                            type="password"
                            name="confirmPassword"
                            placeholder="새 비밀번호를 다시 입력하세요"
                            value={formData.confirmPassword}
                            onChange={handleChange}
                        />
                    </div>

                    {status.message && (
                        <div style={{
                            padding: '16px',
                            borderRadius: '8px',
                            marginBottom: '24px',
                            backgroundColor: status.type === 'success' ? '#DCFCE7' : '#FEE2E2',
                            color: status.type === 'success' ? '#166534' : '#991B1B',
                            fontSize: '0.9rem',
                            fontWeight: '600',
                            textAlign: 'center'
                        }}>
                            {status.message}
                        </div>
                    )}

                    <button type="submit" className="primary" style={{ width: '100%', height: '50px' }}>
                        설정 저장하기
                    </button>
                </form>
            </div>
        </div>
    );
};

export default Profile;
