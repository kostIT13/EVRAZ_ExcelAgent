import { Routes, Route, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import Header from '@/components/layout/Header';
import Background from '@/components/layout/Background';
import AnimatedPage from '@/components/layout/AnimatedPage';
import ChatPage from '@/pages/ChatPage';
import FilesPage from '@/pages/FilesPage';
import TracePage from '@/pages/TracePage';
import DashboardPage from '@/pages/DashboardPage';
import MetricsPage from '@/pages/MetricsPage';

export default function App() {
  const location = useLocation();

  return (
    <div className="app">
      <Background />
      <Header />
      <main className="main">
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
            <Route
              path="/"
              element={
                <AnimatedPage>
                  <ChatPage />
                </AnimatedPage>
              }
            />
            <Route
              path="/dashboard"
              element={
                <AnimatedPage>
                  <DashboardPage />
                </AnimatedPage>
              }
            />
            <Route
              path="/files"
              element={
                <AnimatedPage>
                  <FilesPage />
                </AnimatedPage>
              }
            />
            <Route
              path="/trace"
              element={
                <AnimatedPage>
                  <TracePage />
                </AnimatedPage>
              }
            />
            <Route
              path="/metrics"
              element={
                <AnimatedPage>
                  <MetricsPage />
                </AnimatedPage>
              }
            />
            <Route
              path="*"
              element={
                <AnimatedPage>
                  <ChatPage />
                </AnimatedPage>
              }
            />
          </Routes>
        </AnimatePresence>
      </main>
    </div>
  );
}