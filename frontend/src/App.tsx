import { Component, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Alert, Button, Spin } from 'antd';
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
import ProductPositioning from './pages/ProductPositioning';
import CommerceModule from './pages/CommerceModule';
import MarketAnalysis from './pages/MarketAnalysis';
import AdStrategy from './pages/AdStrategy';
import ListingOptimizeRecords from './pages/ListingOptimizeRecords';
import InventoryLKA from './pages/InventoryLKA';

class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, minHeight: '100vh', background: '#020812' }}>
          <Alert
            type="error"
            message="页面渲染出错"
            description={
              <>
                <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{this.state.error.message}</pre>
                <Button
                  size="small"
                  style={{ marginTop: 8 }}
                  onClick={() => {
                    sessionStorage.clear();
                    window.location.reload();
                  }}
                >
                  清除缓存并刷新
                </Button>
              </>
            }
          />
        </div>
      );
    }
    return this.props.children;
  }
}

function LoadingScreen() {
  return (
    <div className="ai-loading">
      <Spin size="large" />
    </div>
  );
}

function PrivateRoute({ children, minLevel = 1 }: { children: ReactNode; minLevel?: number }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <LoadingScreen />;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (user.permission_level < minLevel) return <Navigate to="/" replace />;

  return <>{children}</>;
}

function PresetRoute({ minLevel = 2 }: { minLevel?: number }) {
  return (
    <PrivateRoute minLevel={minLevel}>
      <CommerceModule />
    </PrivateRoute>
  );
}

function AppRoutes() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <LoadingScreen />;
  if (location.pathname === '/login' && user) return <Navigate to="/" replace />;

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<PrivateRoute><MainLayout /></PrivateRoute>}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/architecture" element={<PresetRoute minLevel={1} />} />
        <Route path="/products" element={<PresetRoute minLevel={2} />} />
        <Route path="/channels" element={<PresetRoute minLevel={2} />} />
        <Route path="/orders" element={<PresetRoute minLevel={2} />} />
        <Route path="/customers" element={<PresetRoute minLevel={2} />} />
        <Route path="/sales" element={<PresetRoute minLevel={2} />} />
        <Route path="/inventory" element={<PrivateRoute minLevel={2}><InventoryLKA /></PrivateRoute>} />
        <Route path="/supply-chain" element={<PresetRoute minLevel={2} />} />
        <Route path="/procurement" element={<PresetRoute minLevel={2} />} />
        <Route path="/warehouse" element={<PresetRoute minLevel={2} />} />
        <Route path="/ads" element={<PrivateRoute minLevel={2}><AdStrategy /></PrivateRoute>} />
        <Route path="/finance-agent/profit" element={<PresetRoute minLevel={2} />} />
        <Route path="/finance-agent/cost" element={<PresetRoute minLevel={2} />} />
        <Route path="/finance-agent/cashflow" element={<PresetRoute minLevel={2} />} />
        <Route path="/product-agent/selection" element={<PresetRoute minLevel={2} />} />
        <Route path="/product-agent/development" element={<PresetRoute minLevel={2} />} />
        <Route path="/product-agent/listing" element={<PresetRoute minLevel={2} />} />
        <Route path="/hr-agent/recruiting" element={<PresetRoute minLevel={2} />} />
        <Route path="/hr-agent/performance" element={<PresetRoute minLevel={2} />} />
        <Route path="/hr-agent/org" element={<PresetRoute minLevel={2} />} />
        <Route path="/workflow" element={<PresetRoute minLevel={3} />} />
        <Route path="/modelops" element={<PresetRoute minLevel={5} />} />
        <Route path="/listing" element={<PrivateRoute minLevel={2}><ListingOptimize /></PrivateRoute>} />
        <Route path="/listing-records" element={<PrivateRoute minLevel={2}><ListingOptimizeRecords /></PrivateRoute>} />
        <Route path="/reviews" element={<PrivateRoute minLevel={2}><ReviewAnalysis /></PrivateRoute>} />
        <Route path="/competitors" element={<PrivateRoute minLevel={2}><CompetitorDiscovery /></PrivateRoute>} />
        <Route path="/market-analysis" element={<PrivateRoute minLevel={2}><MarketAnalysis /></PrivateRoute>} />
        <Route path="/positioning" element={<PrivateRoute minLevel={2}><ProductPositioning /></PrivateRoute>} />
        <Route path="/query" element={<PrivateRoute minLevel={3}><DataQuery /></PrivateRoute>} />
        <Route path="/analysis" element={<PrivateRoute minLevel={3}><DataAnalysis /></PrivateRoute>} />
        <Route path="/rag" element={<PrivateRoute minLevel={4}><RagChat /></PrivateRoute>} />
        <Route path="/system" element={<PrivateRoute minLevel={5}><SystemStatus /></PrivateRoute>} />
        <Route path="/users" element={<PrivateRoute minLevel={5}><UserManagement /></PrivateRoute>} />
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
