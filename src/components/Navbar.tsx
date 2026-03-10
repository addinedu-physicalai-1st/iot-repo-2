import React, { useState } from 'react';

interface NavbarProps {
    onNavChange: (page: string) => void;
    activePage: string;
    onLogout: () => void;
    user: any;
}

const Navbar: React.FC<NavbarProps> = ({ onNavChange, activePage, onLogout, user }) => {
    const [isMenuOpen, setIsMenuOpen] = useState(false);

    const menuItems = [
        { id: 'dashboard', label: '대시보드' },
        { id: 'mycars', label: '내 차량 관리' },
        { id: 'payments', label: '결제 내역' },
        { id: 'guests', label: '방문 예약' },
    ];

    const toggleMenu = () => setIsMenuOpen(!isMenuOpen);

    const handleNav = (id: string) => {
        onNavChange(id);
        setIsMenuOpen(false);
    };

    return (
        <>
            <nav style={{
                backgroundColor: 'rgba(255, 255, 255, 0.85)',
                backdropFilter: 'blur(12px)',
                borderBottom: '1px solid var(--border-color)',
                padding: '0 var(--container-padding)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                position: 'sticky',
                top: '0',
                zIndex: 1000,
                height: 'var(--header-height)',
                transition: 'all 0.3s ease'
            }}>
                <div
                    style={{ fontWeight: '800', fontSize: '1.25rem', color: 'var(--primary-navy)', letterSpacing: '-0.5px', cursor: 'pointer' }}
                    onClick={() => handleNav('dashboard')}
                >
                    SMART <span style={{ color: 'var(--accent-blue)' }}>PARKING</span>
                </div>

                {/* Desktop Menu */}
                <ul className="desktop-menu" style={{
                    display: 'flex',
                    gap: '24px',
                    listStyle: 'none',
                    height: '100%',
                    alignItems: 'center',
                    margin: 0,
                    padding: 0
                }}>
                    {menuItems.map((item) => (
                        <li
                            key={item.id}
                            onClick={() => handleNav(item.id)}
                            style={{
                                cursor: 'pointer',
                                color: activePage === item.id ? 'var(--accent-blue)' : 'var(--text-secondary)',
                                fontWeight: '700',
                                fontSize: '0.85rem',
                                letterSpacing: '0.02em',
                                transition: 'all 0.2s ease',
                                height: '100%',
                                display: 'flex',
                                alignItems: 'center',
                                borderBottom: activePage === item.id ? '2.5px solid var(--accent-blue)' : '2px solid transparent',
                                padding: '0 4px'
                            }}
                        >
                            {item.label}
                        </li>
                    ))}
                </ul>

                <div className="nav-right" style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                    <div
                        onClick={() => handleNav('profile')}
                        className="user-profile-badge"
                        style={{ textAlign: 'right', cursor: 'pointer', padding: '6px 12px', borderRadius: '10px', transition: 'background 0.2s' }}
                    >
                        <div style={{ fontSize: '0.8rem', fontWeight: '800', color: activePage === 'profile' ? 'var(--accent-blue)' : 'var(--primary-navy)' }}>{user.name}</div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', fontWeight: '600' }}>{user.unitNumber}호</div>
                    </div>

                    <button
                        onClick={onLogout}
                        className="secondary logout-btn"
                        style={{ padding: '8px 14px', fontSize: '0.75rem', fontWeight: '700' }}
                    >
                        LOGOUT
                    </button>

                    {/* Mobile Menu Button */}
                    <button
                        className="mobile-menu-toggle"
                        onClick={toggleMenu}
                        style={{
                            display: 'none',
                            background: 'none',
                            border: 'none',
                            padding: '10px',
                            cursor: 'pointer',
                            color: 'var(--primary-navy)'
                        }}
                    >
                        <div style={{ width: '24px', height: '2px', backgroundColor: 'currentColor', marginBottom: '5px', borderRadius: '2px' }}></div>
                        <div style={{ width: '24px', height: '2px', backgroundColor: 'currentColor', marginBottom: '5px', borderRadius: '2px' }}></div>
                        <div style={{ width: '24px', height: '2px', backgroundColor: 'currentColor', borderRadius: '2px' }}></div>
                    </button>
                </div>
            </nav>

            {/* Mobile Sidebar Overlay */}
            {isMenuOpen && (
                <div
                    onClick={toggleMenu}
                    style={{
                        position: 'fixed',
                        top: 0, left: 0, right: 0, bottom: 0,
                        backgroundColor: 'rgba(15, 23, 42, 0.4)',
                        backdropFilter: 'blur(4px)',
                        zIndex: 2000
                    }}
                />
            )}

            {/* Mobile Sidebar - Fixed outside nav for better rendering */}
            <div style={{
                position: 'fixed',
                top: 0,
                right: isMenuOpen ? '0' : '-300px',
                width: '300px',
                height: '100vh',
                backgroundColor: '#ffffff',
                color: '#0F172A',
                zIndex: 2001,
                transition: 'right 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                padding: '40px 32px',
                boxShadow: '-10px 0 50px rgba(0,0,0,0.3)',
                display: 'flex',
                flexDirection: 'column',
                visibility: isMenuOpen ? 'visible' : 'hidden'
            }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '40px' }}>
                    <div style={{ fontWeight: '800', fontSize: '1.4rem', color: 'var(--primary-navy)' }}>
                        MENU
                    </div>
                    <button
                        onClick={toggleMenu}
                        style={{
                            background: 'none',
                            border: 'none',
                            fontSize: '2rem',
                            color: 'var(--text-secondary)',
                            cursor: 'pointer',
                            padding: '0 8px'
                        }}
                    >×</button>
                </div>

                <ul style={{ listStyle: 'none', padding: 0, margin: 0, flex: 1 }}>
                    {menuItems.map((item) => (
                        <li
                            key={item.id}
                            onClick={() => handleNav(item.id)}
                            style={{
                                padding: '20px 0',
                                borderBottom: '1px solid #f1f5f9',
                                color: activePage === item.id ? 'var(--accent-blue)' : 'var(--primary-navy)',
                                fontWeight: '700',
                                fontSize: '1.1rem',
                                cursor: 'pointer'
                            }}
                        >
                            {item.label}
                        </li>
                    ))}
                </ul>

                <div style={{ marginTop: 'auto', borderTop: '2px solid #f1f5f9', paddingTop: '32px' }}>
                    <div style={{ marginBottom: '32px' }}>
                        <div style={{ fontWeight: '800', fontSize: '1.2rem', color: 'var(--primary-navy)' }}>{user.name}</div>
                        <div style={{ fontSize: '0.95rem', color: 'var(--text-secondary)', fontWeight: '600' }}>{user.unitNumber}호 입주민</div>
                    </div>
                    <button
                        onClick={onLogout}
                        style={{
                            width: '100%',
                            backgroundColor: '#fee2e2',
                            color: '#ef4444',
                            fontWeight: '800',
                            padding: '16px',
                            borderRadius: '12px',
                            border: 'none',
                            cursor: 'pointer'
                        }}
                    >
                        로그아웃
                    </button>
                </div>
            </div>

            <style>{`
                @media (max-width: 900px) {
                    .desktop-menu, .logout-btn { display: none !important; }
                    .mobile-menu-toggle { display: block !important; }
                    .user-profile-badge { display: none !important; }
                    .nav-right { gap: 0 !important; }
                }
                
                .user-profile-badge:hover { background-color: var(--light-gray); }
            `}</style>
        </>
    );
};

export default Navbar;
