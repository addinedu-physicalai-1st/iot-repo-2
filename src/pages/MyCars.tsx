import React, { useState, useEffect } from 'react';

interface MyCarsProps {
    user: any;
    onNavigate: (page: string, params?: any) => void;
}

const MyCars: React.FC<MyCarsProps> = ({ user, onNavigate }) => {
    const [cars, setCars] = useState<any[]>([]);
    const [newPlate, setNewPlate] = useState('');
    const [loading, setLoading] = useState(true);

    const fetchCars = async () => {
        try {
            const response = await fetch(`/api/cars?unitNumber=${user.unitNumber}`);
            const data = await response.json();
            setCars(data);
        } catch (error) {
            console.error("차량 목록 페치 실패:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchCars();
    }, [user.unitNumber]);

    const handlePlateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setNewPlate(e.target.value.toUpperCase().replace(/\s/g, ''));
    };

    const registerVehicle = async (e: React.FormEvent) => {
        e.preventDefault();
        if (newPlate) {
            alert('신규 차량 등록 기능은 현재 백엔드 계정 생성 단계에서 지원됩니다.');
            setNewPlate('');
        }
    };

    const toggleVehicleStatus = async (id: number, currentStatus: number) => {
        const action = currentStatus === 1 ? '비활성화' : '활성화';
        if (!window.confirm(`이 차량을 ${action}하시겠습니까?`)) return;

        try {
            const response = await fetch('/api/cars/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id, isActive: currentStatus === 1 ? 0 : 1 })
            });

            if (response.ok) {
                fetchCars();
            } else {
                alert(`${action}에 실패했습니다.`);
            }
        } catch (error) {
            console.error(`${action} 오류:`, error);
        }
    };

    return (
        <div className="page-transition responsive-container">
            <div className="page-header" style={{ marginBottom: '32px' }}>
                <h1 style={{ fontSize: 'clamp(1.75rem, 5vw, 2.5rem)', fontWeight: '800', color: 'var(--primary-navy)', marginBottom: '8px', lineHeight: '1.2' }}>차량 관리</h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: 'clamp(0.9rem, 1.1vw, 1.1rem)' }}>등록 차량 정보 및 상태를 관리하세요.</p>
            </div>

            <div className="card glass-card registration-section" style={{
                marginBottom: '32px',
                padding: 'var(--container-padding)',
                border: 'none',
                background: 'rgba(255, 255, 255, 0.7)',
                backdropFilter: 'blur(12px)'
            }}>
                <div style={{ marginBottom: '20px' }}>
                    <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: '700' }}>신규 차량 등록</h3>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '4px' }}>권한을 추가할 차량 번호를 입력해주세요.</p>
                </div>
                <form onSubmit={registerVehicle} className="mobile-stack" style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1, width: '100%' }}>
                        <input
                            type="text"
                            placeholder="예: 12가3456"
                            value={newPlate}
                            onChange={handlePlateChange}
                            style={{
                                margin: 0,
                                height: '54px',
                                fontSize: '1.05rem',
                                padding: '0 20px',
                                border: '2px solid var(--border-color)',
                                backgroundColor: '#fff'
                            }}
                        />
                    </div>
                    <button type="submit" className="primary mobile-full" style={{ height: '54px', padding: '0 32px', fontSize: '0.95rem', fontWeight: '700', whiteSpace: 'nowrap' }}>
                        등록하기
                    </button>
                </form>
            </div>

            <div className="cars-grid" style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(100%, 1fr))',
                gap: '24px'
            }}>
                {cars.length > 0 ? (
                    cars.map((car) => (
                        <div
                            key={car.id}
                            className={`card car-card ${!car.is_active ? 'deactivated' : ''}`}
                            style={{
                                padding: '0',
                                overflow: 'hidden',
                                display: 'flex',
                                flexDirection: 'column',
                                transition: 'all 0.3s ease',
                                border: '1px solid var(--border-color)',
                                opacity: car.is_active ? 1 : 0.85
                            }}
                        >
                            <div className="car-card-header" style={{
                                padding: '24px 32px',
                                background: car.is_active
                                    ? 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)'
                                    : '#f1f5f9',
                                borderBottom: '1px solid var(--border-color)',
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center'
                            }}>
                                <div>
                                    <div style={{ fontSize: '0.7rem', fontWeight: '800', color: car.is_active ? 'var(--accent-blue)' : 'var(--text-secondary)', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '4px' }}>
                                        PLATE NUMBER
                                    </div>
                                    <h2 style={{ fontSize: '1.8rem', margin: 0, fontWeight: '800', color: car.is_active ? 'var(--primary-navy)' : 'var(--text-secondary)' }}>
                                        {car.plate}
                                    </h2>
                                </div>
                                <div style={{
                                    padding: '6px 14px',
                                    borderRadius: '8px',
                                    backgroundColor: car.is_active ? '#fff' : '#e2e8f0',
                                    fontSize: '0.75rem',
                                    fontWeight: '800',
                                    color: car.is_active ? 'var(--success)' : 'var(--text-secondary)',
                                    border: '1px solid var(--border-color)',
                                    boxShadow: '0 2px 4px rgba(0,0,0,0.05)'
                                }}>
                                    {car.is_active ? 'ACTIVE' : 'DEACTIVATED'}
                                </div>
                            </div>

                            <div className="car-card-body" style={{ padding: '24px 32px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '20px' }}>
                                <div>
                                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: '600', marginBottom: '4px' }}>누적 결제 금액</div>
                                    <div style={{ fontSize: '1.5rem', fontWeight: '800', color: car.is_active ? 'var(--accent-blue)' : 'var(--text-secondary)' }}>
                                        {new Intl.NumberFormat('ko-KR').format(car.total_payment || 0)}
                                        <span style={{ fontSize: '0.9rem', marginLeft: '3px', fontWeight: '600' }}>원</span>
                                    </div>
                                </div>

                                <button
                                    onClick={() => onNavigate('payments', { plate: car.plate })}
                                    className="secondary mobile-full"
                                    style={{
                                        padding: '12px 24px',
                                        fontSize: '0.9rem',
                                        fontWeight: '700',
                                        backgroundColor: car.is_active ? 'var(--white)' : 'var(--light-gray)',
                                        borderColor: car.is_active ? 'var(--primary-navy)' : 'var(--border-color)'
                                    }}
                                >
                                    결제 내역 보기
                                </button>
                            </div>

                            <div className="car-card-footer" style={{
                                padding: '16px 32px',
                                backgroundColor: '#fcfcfc',
                                borderTop: '1px solid var(--border-color)',
                                display: 'flex',
                                justifyContent: 'flex-end',
                                alignItems: 'center',
                                gap: '16px'
                            }}>
                                {!car.is_active ? (
                                    <button
                                        onClick={() => toggleVehicleStatus(car.id, car.is_active)}
                                        className="mobile-full"
                                        style={{
                                            padding: '8px 16px',
                                            backgroundColor: 'var(--success)',
                                            color: '#fff',
                                            borderRadius: '8px',
                                            fontSize: '0.85rem',
                                            fontWeight: '700'
                                        }}
                                    >
                                        다시 활성화하기
                                    </button>
                                ) : (
                                    <button
                                        onClick={() => toggleVehicleStatus(car.id, car.is_active)}
                                        style={{
                                            background: 'none',
                                            color: '#ef4444',
                                            fontSize: '0.85rem',
                                            fontWeight: '600',
                                            padding: '4px 8px',
                                            opacity: 0.7
                                        }}
                                    >
                                        차량 비활성화
                                    </button>
                                )}
                            </div>
                        </div>
                    ))
                ) : (
                    <div style={{ textAlign: 'center', padding: '64px', border: '2px dashed var(--border-color)', borderRadius: '24px' }}>
                        <p style={{ color: 'var(--text-secondary)', fontWeight: '500' }}>등록된 차량이 없습니다.</p>
                    </div>
                )}
            </div>

            <style>{`
                @media (max-width: 640px) {
                    .car-card-header { padding: 20px !important; }
                    .car-card-body { padding: 20px !important; flex-direction: column !important; align-items: flex-start !important; }
                    .car-card-footer { padding: 12px 20px !important; }
                    .car-card-header h2 { font-size: 1.5rem !important; }
                }
            `}</style>
        </div>
    );
};

export default MyCars;
