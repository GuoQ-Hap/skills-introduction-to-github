import { Component, type ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Spin, Alert, Button } from 'antd';
import { AuthProvider, useAuth } from './context/AuthContext';
import { TaskProvider } from './context/TaskContext';
import MainLayout from './layouts/MainLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import ListingOptimize from './pages/ListingOptimize';
import DataQuery from './pages/DataQuery';
import DataAnalysis from './pages/DataAnalysis';
import RagChat from './pages/RagChat';
import SystemStatus from './pages/SystemStatus';
import UserManagement from './pages/UserManagement';
import ReviewAnalysis from './pages/ReviewAnalysis';
import CompetitorDiscovery from './pages/CompetitorDiscovery';

class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40 }}>
          <Alert
            type="error"
            message="页面渲染出错"
            description={
              <>
                <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{this.state.error.message}</pre>
                <pre style={{ fontSize: 11, color: '#888', maxHeight: 200, overflow: 'auto' }}>{this.state.error.stack}</pre>
                <Button size="small" style={{ marginTop: 8 }} onClick={() => {
                  sessionStorage.clear();
                  window.location.reload();
                }}>清除缓存并刷新</Button>
              </>
            }
          />
        </div>
      );
    }
    return this.props.children;
  }
}

function PrivateRoute({ children, minLevel = 1 }: { children: ReactNode; minLevel?: number }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  if (user.permission_level < minLevel) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

function AppRoutes() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f5f5f5' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (location.pathname === '/login' && user) {
    return <Navigate to="/" replace />;
  }

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={
        <PrivateRoute minLevel={1}>
          <MainLayout />
        </PrivateRoute>
      }>
        <Route path="/" element={<Dashboard />} />
        <Route path="/listing" element={
          <PrivateRoute minLevel={2}>
            <ListingOptimize />
          </PrivateRoute>
        } />
        <Route path="/reviews" element={
          <PrivateRoute minLevel={2}>
            <ReviewAnalysis />
          </PrivateRoute>
        } />
        <Route path="/competitors" element={
          <PrivateRoute minLevel={2}>
            <CompetitorDiscovery />
          </PrivateRoute>
        } />
        <Route path="/query" element={
          <PrivateRoute minLevel={3}>
            <DataQuery />
          </PrivateRoute>
        } />
        <Route path="/analysis" element={
          <PrivateRoute minLevel={3}>
            <DataAnalysis />
          </PrivateRoute>
        } />
        <Route path="/rag" element={
          <PrivateRoute minLevel={4}>
            <RagChat />
          </PrivateRoute>
        } />
        <Route path="/system" element={
          <PrivateRoute minLevel={5}>
            <SystemStatus />
          </PrivateRoute>
        } />
        <Route path="/users" element={
          <PrivateRoute minLevel={5}>
            <UserManagement />
          </PrivateRoute>
        } />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <TaskProvider>
            <AppRoutes />
          </TaskProvider>
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;
