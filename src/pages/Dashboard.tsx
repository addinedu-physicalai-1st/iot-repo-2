import React, { useState, useEffect } from 'react';

interface DashboardProps {
    user: any;
}

const Dashboard: React.FC<DashboardProps> = ({ user }) => {
    const [parkingStats, setParkingStats] = useState({
        ground: { total: 0, available: 0 },
        tower: { total: 0, available: 0 },
        myCars: 0
    });
    const [slots, setSlots] = useState<any[]>([]);
    const [userCars, setUserCars] = useState<string[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchDashboardData = async () => {
        try {
            const statsRes = await fetch(`/api/parking/stats?unitNumber=${user.unitNumber}`);
            const statsData = await statsRes.json();

            const slotsRes = await fetch('/api/parking/slots');
            const slotsData = await slotsRes.json();

            const carsRes = await fetch(`/api/cars?unitNumber=${user.unitNumber}`);
            const carsData = await carsRes.json();
            const myPlates = carsData ? carsData.map((c: any) => c.plate) : [];

            setParkingStats({
                ground: statsData.ground || { total: 0, available: 0 },
                tower: statsData.tower || { total: 0, available: 0 },
                myCars: statsData.myCarsCount || 0
            });
            setUserCars(myPlates);

            if (Array.isArray(slotsData)) {
                setSlots(slotsData);
            }
        } catch (error) {
            console.error("데이터 가져오기 실패:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchDashboardData();
        const interval = setInterval(fetchDashboardData, 5000);
        return () => clearInterval(interval);
    }, [user.unitNumber]);

    const isMyCar = (plate: string) => {
        if (!plate) return false;
        return userCars.includes(plate);
    };

    return (
        <div className="page-transition responsive-container">
            {/* Hero Section */}
            <div className="hero-section" style={{
                background: 'linear-gradient(135deg, var(--primary-navy) 0%, #1e293b 100%)',
                borderRadius: '24px',
                padding: 'var(--container-padding)',
                color: '#fff',
                marginBottom: '32px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '24px',
                boxShadow: '0 20px 40px rgba(15, 23, 42, 0.2)'
            }}>
                <div className="hero-text">
                    <h1 style={{
                        fontSize: 'clamp(1.5rem, 5vw, 2.5rem)',
                        marginBottom: '8px',
                        fontWeight: '800',
                        color: '#FFFFFF',
                        letterSpacing: '-0.02em',
                        background: 'none',
                        WebkitTextFillColor: 'initial',
                        lineHeight: '1.2'
                    }}>
                        반갑습니다, {user.name}님
                    </h1>
                    <p style={{ fontSize: 'clamp(0.9rem, 2vw, 1.1rem)', opacity: 0.9, fontWeight: '500', color: '#FFFFFF' }}>
                        {user.unitNumber}호의 실시간 주차 대시보드
                    </p>
                </div>

                <div className="active-cars-badge" style={{
                    background: 'rgba(255, 255, 255, 0.1)',
                    backdropFilter: 'blur(10px)',
                    padding: '20px 32px',
                    borderRadius: '20px',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                    textAlign: 'center',
                    minWidth: '160px'
                }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: '700', opacity: 0.9, marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#FFFFFF' }}>
                        Active Vehicles
                    </div>
                    <div style={{
                        fontSize: '2.5rem',
                        fontWeight: '900',
                        color: '#60a5fa',
                        lineHeight: '1'
                    }}>
                        {loading ? '...' : parkingStats.myCars}
                    </div>
                </div>
            </div>

            {/* Parking Stats Grid */}
            <div className="stats-grid" style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '24px',
                marginBottom: '32px'
            }}>
                <div className="card stat-card" style={{ padding: '24px', display: 'flex', alignItems: 'center', gap: '20px', borderLeft: '4px solid var(--success)' }}>
                    <div className="stat-icon" style={{
                        width: '56px', height: '56px',
                        borderRadius: '14px',
                        backgroundColor: '#ecfdf5',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: '1.3rem', fontWeight: '800', color: 'var(--success)'
                    }}>P</div>
                    <div>
                        <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', fontWeight: '700', marginBottom: '2px' }}>지상 주차 가능</p>
                        <h2 style={{ fontSize: '1.6rem', margin: 0 }}>
                            {loading ? '...' : parkingStats.ground.available} <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', fontWeight: '500' }}>/ {parkingStats.ground.total}</span>
                        </h2>
                    </div>
                </div>

                <div className="card stat-card" style={{ padding: '24px', display: 'flex', alignItems: 'center', gap: '20px', borderLeft: '4px solid var(--accent-blue)' }}>
                    <div className="stat-icon" style={{
                        width: '56px', height: '56px',
                        borderRadius: '14px',
                        backgroundColor: '#eff6ff',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: '1.3rem', fontWeight: '800', color: 'var(--accent-blue)'
                    }}>T</div>
                    <div>
                        <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', fontWeight: '700', marginBottom: '2px' }}>타워 주차 가능</p>
                        <h2 style={{ fontSize: '1.6rem', margin: 0 }}>
                            {loading ? '...' : parkingStats.tower.available} <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', fontWeight: '500' }}>/ {parkingStats.tower.total}</span>
                        </h2>
                    </div>
                </div>
            </div>

            {/* Real-time Parking Map */}
            <div className="card map-card" style={{ padding: 'var(--container-padding)', backgroundColor: '#fff' }}>
                <div className="map-header" style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '32px',
                    flexWrap: 'wrap',
                    gap: '20px'
                }}>
                    <div>
                        <h3 style={{ fontSize: 'clamp(1.2rem, 3vw, 1.5rem)', margin: 0 }}>실시간 주차 맵</h3>
                        <p style={{ color: 'var(--text-secondary)', marginTop: '4px', fontSize: '0.9rem' }}>점유 상태 모니터링</p>
                    </div>
                    <div className="map-legend" style={{
                        display: 'flex',
                        gap: '16px',
                        padding: '10px 16px',
                        backgroundColor: '#f8fafc',
                        borderRadius: '10px',
                        border: '1px solid var(--border-color)',
                        fontSize: '0.8rem'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: '600' }}>
                            <div style={{ width: '12px', height: '12px', background: '#FFFFFF', border: '1.5px dashed #cbd5e1', borderRadius: '3px' }}></div>
                            OPEN
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: '600' }}>
                            <div style={{ width: '12px', height: '12px', background: 'var(--accent-blue)', borderRadius: '3px' }}></div>
                            BUSY
                        </div>
                    </div>
                </div>

                <div className="map-sections-grid" style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
                    gap: '32px'
                }}>
                    {/* 지상 주차장 */}
                    <div className="parking-section">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
                            <h4 style={{ margin: 0, fontSize: '0.8rem', fontWeight: '800', color: 'var(--text-secondary)' }}>STREET</h4>
                            <div style={{ flex: 1, height: '1px', background: 'var(--border-color)' }}></div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '16px' }}>
                            {slots.filter(s => s.level === 'street').map((slot) => (
                                <div key={slot.name} className={`parking-space-mini ${slot.is_occupied ? 'occupied' : 'empty'}`}>
                                    <div className="mini-header">
                                        <span>{slot.name}</span>
                                        {slot.is_occupied && <span className="occupied-dot"></span>}
                                    </div>
                                    <div className="mini-content">
                                        {slot.is_occupied ? (
                                            <div className={`car-plate-mini ${isMyCar(slot.last_vehicle_plate) ? 'mine' : ''}`}>
                                                {isMyCar(slot.last_vehicle_plate) ? slot.last_vehicle_plate : 'P'}
                                            </div>
                                        ) : (
                                            <span className="open-text">OPEN</span>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* 타워 주차장 */}
                    <div className="parking-section">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
                            <h4 style={{ margin: 0, fontSize: '0.8rem', fontWeight: '800', color: 'var(--accent-blue)' }}>TOWER</h4>
                            <div style={{ flex: 1, height: '1px', background: 'var(--border-color)' }}></div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', gap: '12px' }}>
                            {slots.filter(s => s.level === 'tower').map((slot) => (
                                <div key={slot.name} className={`parking-space-mini thin ${slot.is_occupied ? 'occupied' : 'empty'}`}>
                                    <div className="mini-header">
                                        <span>{slot.name}</span>
                                    </div>
                                    <div className="mini-content">
                                        {slot.is_occupied ? (
                                            <div className={`car-plate-mini sm ${isMyCar(slot.last_vehicle_plate) ? 'mine' : ''}`}>
                                                {isMyCar(slot.last_vehicle_plate) ? slot.last_vehicle_plate : 'P'}
                                            </div>
                                        ) : (
                                            <span className="open-text sm">OPEN</span>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            <style>{`
                .parking-space-mini {
                    height: 100px;
                    border-radius: 12px;
                    padding: 12px;
                    display: flex;
                    flex-direction: column;
                    justify-content: space-between;
                    background: #fff;
                    transition: all 0.2s ease;
                }
                .parking-space-mini.thin { height: 90px; }
                .parking-space-mini.empty {
                    border: 1.5px dashed var(--border-color);
                }
                .parking-space-mini.occupied {
                    border: 1.5px solid var(--accent-blue);
                    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.08);
                }
                .mini-header {
                    display: flex;
                    justify-content: space-between;
                    font-size: 0.65rem;
                    font-weight: 800;
                    color: var(--text-secondary);
                }
                .occupied-dot {
                    width: 6px;
                    height: 6px;
                    border-radius: 50%;
                    background: var(--danger);
                }
                .mini-content {
                    flex: 1;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .car-plate-mini {
                    width: 100%;
                    height: 100%;
                    background: #64748b;
                    color: #fff;
                    border-radius: 6px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 0.8rem;
                    font-weight: 700;
                }
                .car-plate-mini.mine {
                    background: var(--accent-blue);
                }
                .car-plate-mini.sm { font-size: 0.7rem; }
                .open-text {
                    color: #cbd5e1;
                    font-size: 0.75rem;
                    font-weight: 700;
                    letter-spacing: 0.05em;
                }
                .open-text.sm { font-size: 0.6rem; }
                
                @media (max-width: 480px) {
                    .hero-section { border-radius: 0; margin: -24px -16px 24px -16px; }
                    .stats-grid { grid-template-columns: 1fr; }
                    .map-card { padding: 20px 16px; }
                    .parking-space-mini { height: 80px; }
                }
            `}</style>
        </div>
    );
};

export default Dashboard;
