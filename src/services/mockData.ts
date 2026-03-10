export interface Resident {
    id: number;
    unit_number: string;
    name: string;
    phone: string;
    car_plate: string;
}

export interface PaymentRecord {
    id: number;
    car_plate: string;
    amount: number;
    date: string;
    status: 'Paid' | 'Pending';
}

export interface GuestVisit {
    id: number;
    car_plate: string;
    unit_number: string;
    arrival_time?: string;
    departure_time?: string;
    status: 'Requested' | 'Approved' | 'Rejected' | 'Visited';
}

export const mockResidents: Resident[] = [
    { id: 1, unit_number: '101-101', name: '홍길동', phone: '010-1111-1111', car_plate: '12가1234' },
    { id: 2, unit_number: '101-102', name: '김철수', phone: '010-2222-2222', car_plate: '23나2345' },
];

export const mockPayments: PaymentRecord[] = [
    { id: 1, car_plate: '12가1234', amount: 5000, date: '2026-03-09 14:00', status: 'Paid' },
    { id: 2, car_plate: '12가1234', amount: 3000, date: '2026-03-08 09:30', status: 'Paid' },
    { id: 3, car_plate: '23나2345', amount: 12000, date: '2026-03-07 18:20', status: 'Pending' },
];

export const mockGuestVisits: GuestVisit[] = [
    { id: 1, car_plate: '55허5555', unit_number: '101-101', status: 'Approved', arrival_time: '2026-03-10 10:00' },
    { id: 2, car_plate: '99어9999', unit_number: '101-102', status: 'Requested' },
];
