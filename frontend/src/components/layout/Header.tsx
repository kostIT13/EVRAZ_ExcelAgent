import { NavLink } from 'react-router-dom';
import { MessageSquare, FolderOpen, Search, LayoutDashboard, Gauge } from 'lucide-react';
import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { checkHealth } from '@/api';

const navItems = [
  { to: '/', label: 'Чат', icon: MessageSquare },
  { to: '/dashboard', label: 'Дашборд', icon: LayoutDashboard },
  { to: '/files', label: 'Файлы', icon: FolderOpen },
  { to: '/trace', label: 'Трассировка', icon: Search },
  { to: '/metrics', label: 'Метрики', icon: Gauge },
];

export default function Header() {
  const [health, setHealth] = useState<'checking' | 'ok' | 'error'>('checking');

  useEffect(() => {
    const check = async () => {
      try {
        await checkHealth();
        setHealth('ok');
      } catch {
        setHealth('error');
      }
    };
    check();
    const t = setInterval(check, 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="header">
      <div className="header__inner">
        <motion.div
          className="header__logo"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4 }}
        >
          <div className="header__logo-icon">Е</div>
          <div className="header__logo-text">
            <h1 className="header__title">ЕВРАЗ AI Agent</h1>
            <span className="header__subtitle">Интеллектуальный анализ Excel-данных</span>
          </div>
        </motion.div>

        <nav className="nav">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => `nav__item${isActive ? ' nav__item--active' : ''}`}
            >
              <Icon size={16} strokeWidth={2} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className={`header__status header__status--${health}`}>
          <span className={`status-dot status-dot--${health}`} />
          <span>
            {health === 'checking' && 'Проверка подключения...'}
            {health === 'ok' && 'Сервер работает'}
            {health === 'error' && 'Нет подключения'}
          </span>
        </div>
      </div>
    </header>
  );
}