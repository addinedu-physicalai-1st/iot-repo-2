import React, { useState, useEffect } from 'react';

interface GuestVisitsProps {
    user: any;
}

const GuestVisits: React.FC<GuestVisitsProps> = ({ user }) => {
    const [guestVisits, setGuestVisits] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchGuestVisits = async () => {
        try {
            const response = await fetch(`/api/guests?unitNumber=${user.unitNumber}`);
            const data = await response.json();
            setGuestVisits(data);
        } catch (error) {
            console.error("방문 예약 페치 실패:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchGuestVisits();
    }, [user.unitNumber]);

    const handleAction = async (id: number, action: string) => {
        try {
            const response = await fetch(`/api/guests/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: action })
            });

            if (response.ok) {
                // 리스트 새로고침
                fetchGuestVisits();
            } else {
                alert('상태 업데이트에 실패했습니다.');
            }
        } catch (error) {
            console.error('방문 예약 업데이트 오류:', error);
            alert('서버와 통신 중 오류가 발생했습니다.');
        }
    };

    const [newVisit, setNewVisit] = useState({ carPlate: '', arrivalTime: '' });

    const handlePlateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setNewVisit({ ...newVisit, carPlate: e.target.value.toUpperCase().replace(/\s/g, '') });
    };

    const handleRegister = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!newVisit.carPlate || !newVisit.arrivalTime) {
            alert('정보를 모두 입력해주세요.');
            return;
        }

        try {
            const response = await fetch('/api/guests', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    carPlate: newVisit.carPlate,
                    arrivalTime: newVisit.arrivalTime,
                    unitNumber: user.unitNumber
                }),
            });

            if (response.ok) {
                alert('방문 예약이 등록되었습니다.');
                setNewVisit({ carPlate: '', arrivalTime: '' });
                fetchGuestVisits();
            } else {
                alert('등록에 실패했습니다.');
            }
        } catch (error) {
            console.error('방문 예약 등록 오류:', error);
        }
    };

    return (
        <div className="page-transition">
            <div style={{ marginBottom: '40px' }}>
                <h1>방문 예약 관리</h1>
                <p style={{ color: 'var(--text-secondary)' }}>외부 차량의 방문 예약을 등록하거나 승인 상태를 관리할 수 있습니다.</p>
            </div>

            <div className="card" style={{ marginBottom: '48px', borderLeft: '4px solid var(--accent-blue)' }}>
                <h3 style={{ marginBottom: '16px' }}>신규 방문 예약 등록</h3>
                <form onSubmit={handleRegister} style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'flex-end' }}>
                    <div style={{ flex: 1, minWidth: '240px' }}>
                        <label>방문 차량 번호</label>
                        <input
                            type="text"
                            placeholder="예: 12가3456"
                            value={newVisit.carPlate}
                            onChange={handlePlateChange}
                            style={{ marginBottom: 0 }}
                        />
                    </div>
                    <div style={{ flex: 1, minWidth: '240px' }}>
                        <label>방문 예정 일시</label>
                        <input
                            type="datetime-local"
                            value={newVisit.arrivalTime}
                            onChange={(e) => setNewVisit({ ...newVisit, arrivalTime: e.target.value })}
                            style={{ marginBottom: 0 }}
                        />
                    </div>
                    <button type="submit" className="primary" style={{ height: '48px', padding: '0 32px' }}>
                        신규 등록
                    </button>
                </form>
            </div>

            <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
                <div style={{ padding: '24px', borderBottom: '1px solid var(--border-color)' }}>
                    <h3 style={{ margin: 0 }}>예약 요청 목록</h3>
                </div>

                <div style={{ overflowX: 'auto' }}>
                    <table style={{ margin: '0', width: '100%' }}>
                        <thead style={{ background: 'var(--light-gray)' }}>
                            <tr>
                                <th style={{ padding: '16px 24px', textAlign: 'left' }}>차량 번호</th>
                                <th style={{ padding: '16px 24px', textAlign: 'left' }}>예상 도착 시간</th>
                                <th style={{ padding: '16px 24px', textAlign: 'center' }}>상태</th>
                                <th style={{ padding: '16px 24px', textAlign: 'right' }}>관리</th>
                            </tr>
                        </thead>
                        <tbody>
                            {guestVisits.length > 0 ? (
                                guestVisits.map((visit) => (
                                    <tr key={visit.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                                        <td style={{ padding: '20px 24px', fontWeight: '700', color: 'var(--primary-navy)' }}>{visit.car_plate}</td>
                                        <td style={{ padding: '20px 24px', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>{visit.arrival_time || '미정'}</td>
                                        <td style={{ padding: '20px 24px', textAlign: 'center' }}>
                                            <span style={{
                                                padding: '6px 12px',
                                                borderRadius: '20px',
                                                fontSize: '0.75rem',
                                                fontWeight: '800',
                                                backgroundColor:
                                                    visit.status === '승인됨' ? '#DCFCE7' :
                                                        visit.status === '거절됨' ? '#FEE2E2' : '#FEF3C7',
                                                color:
                                                    visit.status === '승인됨' ? '#166534' :
                                                        visit.status === '거절됨' ? '#991B1B' : '#92400E'
                                            }}>
                                                {visit.status === '승인됨' ? 'APPROVED' :
                                                    visit.status === '거절됨' ? 'REJECTED' : 'WAITING'}
                                            </span>
                                        </td>
                                        <td style={{ padding: '20px 24px', textAlign: 'right' }}>
                                            {visit.status === '승인대기' && (
                                                <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                                                    <button
                                                        onClick={() => handleAction(visit.id, '승인됨')}
                                                        className="primary"
                                                        style={{ padding: '6px 16px', fontSize: '0.8rem', background: 'var(--success)' }}
                                                    >
                                                        ACCEPT
                                                    </button>
                                                    <button
                                                        onClick={() => handleAction(visit.id, '거절됨')}
                                                        className="secondary"
                                                        style={{ padding: '6px 16px', fontSize: '0.8rem', color: 'var(--danger)', borderColor: 'var(--danger)' }}
                                                    >
                                                        REJECT
                                                    </button>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={4} style={{ padding: '60px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                                        예약된 방문 정보가 없습니다.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            <div className="card" style={{ marginTop: '30px' }}>
                <h3>방문 내역</h3>
                <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>과거에 방문했던 게스트 차량의 로그입니다.</p>
                <div style={{ marginTop: '20px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                    최근 방문 내역이 없습니다.
                </div>
            </div>
        </div>
    );
};

export default GuestVisits;
