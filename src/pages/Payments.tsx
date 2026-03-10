import React, { useState, useEffect } from 'react';

interface PaymentsProps {
    user: any;
    initialParams?: any;
}

const Payments: React.FC<PaymentsProps> = ({ user, initialParams }) => {
    const [records, setRecords] = useState<any[]>([]);
    const [filteredRecords, setFilteredRecords] = useState<any[]>([]);
    const [balance, setBalance] = useState<number>(0);
    const [loading, setLoading] = useState(true);
    const [depositAmount, setDepositAmount] = useState<string>('');
    const [isCharging, setIsCharging] = useState(false);
    const [searchPlate, setSearchPlate] = useState(initialParams?.plate || '');

    // 카드 관련 상태
    const [cards, setCards] = useState<any[]>([]);
    const [showCardForm, setShowCardForm] = useState(false);
    const [newCard, setNewCard] = useState({ cardType: '신한카드', cardNumber: '', expiry: '' });

    const fetchPayments = async () => {
        try {
            const response = await fetch(`/api/payments?unitNumber=${user.unitNumber}`);
            const data = await response.json();
            setRecords(data);
        } catch (error) {
            console.error("결제 내역 페치 실패:", error);
        } finally {
            setLoading(false);
        }
    };

    const fetchBalance = async () => {
        try {
            const response = await fetch(`/api/user/balance?phone=${user.phone}`);
            const data = await response.json();
            setBalance(data.balance);
        } catch (error) {
            console.error("잔액 페치 실패:", error);
        }
    };

    const fetchCards = async () => {
        try {
            const response = await fetch(`/api/cards?phone=${user.phone}`);
            const data = await response.json();
            setCards(data);
        } catch (error) {
            console.error("카드 목록 페치 실패:", error);
        }
    };

    useEffect(() => {
        fetchPayments();
        fetchBalance();
        fetchCards();
    }, [user.unitNumber, user.phone]);

    useEffect(() => {
        if (searchPlate) {
            setFilteredRecords(records.filter((r: any) =>
                r.car_plate.toUpperCase().includes(searchPlate.toUpperCase())
            ));
        } else {
            setFilteredRecords(records);
        }
    }, [searchPlate, records]);

    const handleCardChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value } = e.target;
        let formattedValue = value;

        if (name === 'cardNumber') {
            const digits = value.replace(/\D/g, '').slice(0, 16);
            formattedValue = digits.match(/.{1,4}/g)?.join('-') || digits;
        } else if (name === 'expiry') {
            const digits = value.replace(/\D/g, '').slice(0, 4);
            if (digits.length >= 2) {
                formattedValue = `${digits.slice(0, 2)}/${digits.slice(2)}`;
            } else {
                formattedValue = digits;
            }
        }
        setNewCard({ ...newCard, [name]: formattedValue });
    };

    const handleAddCard = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!newCard.cardNumber || !newCard.expiry) {
            alert('카드 정보를 모두 입력해주세요.');
            return;
        }

        try {
            const response = await fetch('/api/cards', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    phone: user.phone,
                    ...newCard
                }),
            });

            if (response.ok) {
                alert('카드가 등록되었습니다.');
                setShowCardForm(false);
                setNewCard({ cardType: '신한카드', cardNumber: '', expiry: '' });
                fetchCards();
            } else {
                alert('카드 등록에 실패했습니다.');
            }
        } catch (error) {
            console.error('카드 등록 오류:', error);
        }
    };

    const handleDeleteCard = async (id: number) => {
        if (!window.confirm('이 카드를 삭제하시겠습니까?')) return;
        try {
            const response = await fetch(`/api/cards/${id}`, { method: 'DELETE' });
            if (response.ok) {
                fetchCards();
            }
        } catch (error) {
            console.error('카드 삭제 오류:', error);
        }
    };

    const handleDeposit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (cards.length === 0) {
            alert('먼저 결제 카드를 등록해주세요.');
            return;
        }

        const amount = parseInt(depositAmount);
        if (isNaN(amount) || amount <= 0) {
            alert('유효한 금액을 입력해주세요.');
            return;
        }

        setIsCharging(true);
        try {
            const response = await fetch('/api/payments/deposit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    phone: user.phone,
                    amount: amount,
                    unitNumber: user.unitNumber,
                    carPlate: user.carPlate || (records.length > 0 ? records[0].car_plate : '-')
                }),
            });

            if (response.ok) {
                alert(`성공적으로 충전되었습니다! (보너스 10% 포함)`);
                setDepositAmount('');
                fetchPayments();
                fetchBalance();
            } else {
                alert('충전에 실패했습니다.');
            }
        } catch (error) {
            console.error('충전 오류:', error);
        } finally {
            setIsCharging(false);
        }
    };

    const formatAmount = (amt: number) => {
        return new Intl.NumberFormat('ko-KR').format(amt) + '원';
    };

    const formatDate = (dateStr: string) => {
        if (!dateStr) return '-';
        return dateStr.replace('T', ' ').split('.')[0];
    };

    return (
        <div className="page-transition">
            <div style={{ marginBottom: '40px' }}>
                <h1>결제 및 충전</h1>
                <p style={{ color: 'var(--text-secondary)' }}>주차 예치금을 충전하고 결제 내역을 확인할 수 있습니다.</p>
            </div>

            <div style={{ marginBottom: '48px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <h3 style={{ margin: 0 }}>내 결제 카드 관리</h3>
                    {!showCardForm && (
                        <button
                            className="secondary"
                            style={{ padding: '8px 16px', fontSize: '0.85rem' }}
                            onClick={() => setShowCardForm(true)}
                        >
                            카드 추가 등록
                        </button>
                    )}
                </div>

                {showCardForm && (
                    <div className="card glass-card" style={{ marginBottom: '24px', position: 'relative' }}>
                        <button
                            onClick={() => setShowCardForm(false)}
                            style={{ position: 'absolute', top: '16px', right: '16px', background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
                        >
                            닫기
                        </button>
                        <h4 style={{ marginBottom: '20px' }}>새 카드 등록</h4>
                        <form onSubmit={handleAddCard} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
                            <div>
                                <label>카드사</label>
                                <select
                                    value={newCard.cardType}
                                    onChange={(e) => setNewCard({ ...newCard, cardType: e.target.value })}
                                    style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-color)', outline: 'none' }}
                                >
                                    <option>신한카드</option>
                                    <option>국민카드</option>
                                    <option>삼성카드</option>
                                    <option>현대카드</option>
                                    <option>비씨카드</option>
                                    <option>하나카드</option>
                                    <option>롯데카드</option>
                                </select>
                            </div>
                            <div>
                                <label>카드 번호</label>
                                <input
                                    type="text"
                                    name="cardNumber"
                                    placeholder="0000-0000-0000-0000"
                                    value={newCard.cardNumber}
                                    onChange={handleCardChange}
                                />
                            </div>
                            <div>
                                <label>유효 기간</label>
                                <input
                                    type="text"
                                    name="expiry"
                                    placeholder="MM/YY"
                                    value={newCard.expiry}
                                    onChange={handleCardChange}
                                />
                            </div>
                            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                                <button type="submit" className="primary" style={{ width: '100%', height: '48px' }}>카드 등록 완료</button>
                            </div>
                        </form>
                    </div>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>
                    {cards.length > 0 ? (
                        cards.map((card) => (
                            <div key={card.id} className="card" style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                background: card.is_default ? 'linear-gradient(135deg, #1e293b 0%, #334155 100%)' : 'var(--card-bg)',
                                color: card.is_default ? '#fff' : 'inherit'
                            }}>
                                <div>
                                    <div style={{ fontSize: '0.8rem', opacity: 0.8, marginBottom: '4px' }}>{card.card_type}</div>
                                    <div style={{ fontSize: '1.1rem', fontWeight: '700', letterSpacing: '2px' }}>
                                        **** **** **** {card.card_number.slice(-4)}
                                    </div>
                                    {card.is_default && (
                                        <div style={{
                                            display: 'inline-block',
                                            fontSize: '0.65rem',
                                            background: 'var(--accent-blue)',
                                            color: '#fff',
                                            padding: '2px 8px',
                                            borderRadius: '4px',
                                            marginTop: '8px',
                                            fontWeight: '700'
                                        }}>
                                            DEFAULT CARD
                                        </div>
                                    )}
                                </div>
                                <button
                                    onClick={() => handleDeleteCard(card.id)}
                                    style={{
                                        background: 'none',
                                        border: 'none',
                                        color: card.is_default ? '#f87171' : 'var(--danger)',
                                        cursor: 'pointer',
                                        fontSize: '0.8rem',
                                        fontWeight: '600'
                                    }}
                                >
                                    삭제
                                </button>
                            </div>
                        ))
                    ) : (
                        <div className="card" style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '40px', border: '2px dashed var(--border-color)', background: 'transparent' }}>
                            <p style={{ color: 'var(--text-secondary)' }}>등록된 결제 카드가 없습니다. 충전을 위해 카드를 먼저 등록해주세요.</p>
                        </div>
                    )}
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px', marginBottom: '48px' }}>
                <div className="card" style={{ borderLeft: '4px solid var(--accent-blue)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', fontWeight: '800', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>현재 예치금 잔액</p>
                    <h2 style={{ fontSize: '2.5rem', margin: 0, fontWeight: '700', color: 'var(--primary-navy)' }}>{formatAmount(balance)}</h2>
                </div>

                <div className="card" style={{ gridColumn: 'span 2' }}>
                    <h3 style={{ marginBottom: '4px' }}>예치금 충전 (10% 보너스)</h3>
                    <p style={{ color: 'var(--text-secondary)', marginBottom: '24px', fontSize: '0.9rem' }}>
                        {cards.length > 0 ? '등록된 카드로 안전하게 충전할 수 있습니다.' : '카드를 먼저 등록해야 충전이 가능합니다.'}
                    </p>

                    <form onSubmit={handleDeposit} style={{ display: 'flex', gap: '16px', alignItems: 'flex-end' }}>
                        <div style={{ flex: 1 }}>
                            <label>충전 금액</label>
                            <input
                                type="number"
                                placeholder="충전할 금액 입력"
                                value={depositAmount}
                                onChange={(e) => setDepositAmount(e.target.value)}
                                style={{ marginBottom: 0 }}
                                disabled={cards.length === 0}
                            />
                        </div>
                        <div style={{ padding: '0 12px 14px 0', fontSize: '0.9rem', color: 'var(--success)', fontWeight: '700' }}>
                            {depositAmount ? `+ ${formatAmount(Math.floor(parseInt(depositAmount) * 0.1))} (BONUS)` : ''}
                        </div>
                        <button
                            type="submit"
                            className="primary"
                            style={{ height: '48px', padding: '0 32px' }}
                            disabled={isCharging || cards.length === 0}
                        >
                            {isCharging ? '처리 중...' : '예치금 충전하기'}
                        </button>
                    </form>
                </div>
            </div>

            <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
                <div style={{ padding: '24px', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
                    <h3 style={{ margin: 0 }}>결제 및 충전 내역</h3>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <div style={{ position: 'relative' }}>
                            <input
                                type="text"
                                placeholder="차량 번호 검색"
                                value={searchPlate}
                                onChange={(e) => setSearchPlate(e.target.value)}
                                style={{ margin: 0, padding: '8px 12px', paddingRight: '32px', fontSize: '0.85rem', width: '180px' }}
                            />
                            {searchPlate && (
                                <button
                                    onClick={() => setSearchPlate('')}
                                    style={{ position: 'absolute', right: '8px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '1rem' }}
                                >
                                    ×
                                </button>
                            )}
                        </div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: '500' }}>{filteredRecords.length}건</div>
                    </div>
                </div>

                <div style={{ overflowX: 'auto' }}>
                    <table style={{ margin: '0', width: '100%' }}>
                        <thead style={{ background: 'var(--light-gray)' }}>
                            <tr>
                                <th style={{ padding: '16px 24px', textAlign: 'left' }}>차량 번호</th>
                                <th style={{ padding: '16px 24px', textAlign: 'left' }}>일시</th>
                                <th style={{ padding: '16px 24px', textAlign: 'left' }}>유형/수단</th>
                                <th style={{ padding: '16px 24px', textAlign: 'right' }}>금액</th>
                                <th style={{ padding: '16px 24px', textAlign: 'center' }}>상태</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredRecords.length > 0 ? (
                                filteredRecords.map((record) => (
                                    <tr key={record.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                                        <td style={{ padding: '20px 24px', fontWeight: '700', color: 'var(--primary-navy)' }}>{record.car_plate}</td>
                                        <td style={{ padding: '20px 24px', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>{formatDate(record.payment_date)}</td>
                                        <td style={{ padding: '20px 24px', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>{record.method || '-'}</td>
                                        <td style={{ padding: '20px 24px', textAlign: 'right', fontWeight: '800', color: record.method?.includes('보너스') ? 'var(--success)' : 'var(--accent-blue)' }}>
                                            {formatAmount(record.amount)}
                                        </td>
                                        <td style={{ padding: '20px 24px', textAlign: 'center' }}>
                                            <span style={{
                                                padding: '6px 12px',
                                                borderRadius: '20px',
                                                fontSize: '0.75rem',
                                                fontWeight: '800',
                                                backgroundColor: record.status === '결제완료' ? '#DCFCE7' : '#FEF3C7',
                                                color: record.status === '결제완료' ? '#166534' : '#92400E'
                                            }}>
                                                {record.status === '결제완료' ? '결제완료' : '대기중'}
                                            </span>
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={5} style={{ padding: '60px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                                        {searchPlate ? '검색 결과가 없습니다.' : '결제 내역이 없습니다.'}
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default Payments;
