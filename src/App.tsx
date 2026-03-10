import React, { useState, useEffect } from 'react';
import './index.css';
import Dashboard from './pages/Dashboard';
import MyCars from './pages/MyCars';
import Payments from './pages/Payments';
import GuestVisits from './pages/GuestVisits';
import Navbar from './components/Navbar';
import Auth from './pages/Auth';
import Profile from './pages/Profile';

function App() {
    const [user, setUser] = useState<any>(null);
    const [activePage, setActivePage] = useState('dashboard');
    const [pageParams, setPageParams] = useState<any>(null);

    // Load user from local storage on mount (optional mock)
    useEffect(() => {
        const savedUser = localStorage.getItem('user');
        if (savedUser) {
            setUser(JSON.parse(savedUser));
        }
    }, []);

    const handleLogin = (userData: any) => {
        setUser(userData);
        localStorage.setItem('user', JSON.stringify(userData));
    };

    const handleLogout = () => {
        setUser(null);
        localStorage.removeItem('user');
        setActivePage('dashboard');
        setPageParams(null);
    };

    const handleUpdateUser = (userData: any) => {
        setUser(userData);
        localStorage.setItem('user', JSON.stringify(userData));
    };

    const handleNavigate = (page: string, params: any = null) => {
        setActivePage(page);
        setPageParams(params);
    };

    const renderPage = () => {
        switch (activePage) {
            case 'dashboard': return <Dashboard user={user} />;
            case 'mycars': return <MyCars user={user} onNavigate={handleNavigate} />;
            case 'payments': return <Payments user={user} initialParams={pageParams} />;
            case 'guests': return <GuestVisits user={user} />;
            case 'profile': return <Profile user={user} onUpdateUser={handleUpdateUser} />;
            default: return <Dashboard user={user} />;
        }
    }

    if (!user) {
        return (
            <div className="App">
                <main className="container">
                    <Auth onLogin={handleLogin} />
                </main>
            </div>
        );
    }

    return (
        <div className="App">
            <Navbar onNavChange={setActivePage} activePage={activePage} onLogout={handleLogout} user={user} />
            <main className="container">
                {renderPage()}
            </main>
        </div>
    );
}

export default App;
