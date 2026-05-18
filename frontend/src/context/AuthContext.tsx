import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import api from '../api';

export interface UserInfo {
  username: string;
  display_name: string;
  permission_level: number;
  permission_name: string;
  enabled: boolean;
  custom_permissions?: string[] | null;
  data_restrictions?: Record<string, string[]> | null;
}

/**
 * 权限等级说明：
 * 1 - 基础用户：用户导航
 * 2 - 操作员：用户导航 + LEANG-AGENT
 * 3 - 分析师：用户导航 + LEANG-AGENT + LEANG-DATA
 * 4 - 高级用户：用户导航 + LEANG-AGENT + LEANG-DATA + LEANG-RAG
 * 5 - 超级管理员：全部功能 + 用户管理
 */

export const PERMISSION_LEVELS = [
  { value: 1, label: '基础用户', description: '仅可访问用户导航' },
  { value: 2, label: '操作员', description: '用户导航 + LEANG-AGENT' },
  { value: 3, label: '分析师', description: '用户导航 + LEANG-AGENT + LEANG-DATA' },
  { value: 4, label: '高级用户', description: '用户导航 + LEANG-AGENT + LEANG-DATA + LEANG-RAG' },
  { value: 5, label: '超级管理员', description: '全部功能 + 用户管理' },
];

export const PERMISSION_COLORS: Record<number, string> = {
  1: '#8d8d8d',
  2: '#1677ff',
  3: '#52c41a',
  4: '#722ed1',
  5: '#f5222d',
};

interface AuthContextType {
  user: UserInfo | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  hasPermission: (minLevel: number) => boolean;
  canAccess: (feature: 'agent' | 'data' | 'rag' | 'system' | 'admin') => boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

const TOKEN_KEY = 'leang_auth_token';
const USER_INFO_KEY = 'leang_user_info';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [loading, setLoading] = useState(true);

  const clearAuth = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_INFO_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const logout = useCallback(() => {
    const t = localStorage.getItem(TOKEN_KEY);
    if (t) {
      fetch('/auth/logout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${t}` },
      }).catch(() => {});
    }
    clearAuth();
  }, [clearAuth]);

  useEffect(() => {
    const handler = () => clearAuth();
    window.addEventListener('auth:expired', handler);
    return () => window.removeEventListener('auth:expired', handler);
  }, [clearAuth]);

  useEffect(() => {
    const savedToken = localStorage.getItem(TOKEN_KEY);
    if (!savedToken) {
      setLoading(false);
      return;
    }
    api.get('/auth/me', { headers: { Authorization: `Bearer ${savedToken}` } })
      .then(res => {
        setUser(res.data);
        setToken(savedToken);
        localStorage.setItem(USER_INFO_KEY, JSON.stringify(res.data));
      })
      .catch(() => {
        clearAuth();
      })
      .finally(() => setLoading(false));
  }, [clearAuth]);

  const login = async (username: string, password: string) => {
    const res = await api.post('/auth/login', { username, password });
    const { token: newToken, ...userInfo } = res.data;
    localStorage.setItem(TOKEN_KEY, newToken);
    localStorage.setItem(USER_INFO_KEY, JSON.stringify(userInfo));
    setToken(newToken);
    setUser(userInfo);
  };

  const refreshUser = useCallback(async () => {
    const t = localStorage.getItem(TOKEN_KEY);
    if (!t) return;
    const res = await api.get('/auth/me', { headers: { Authorization: `Bearer ${t}` } });
    setUser(res.data);
    localStorage.setItem(USER_INFO_KEY, JSON.stringify(res.data));
  }, []);

  const hasPermission = useCallback((minLevel: number) => {
    return (user?.permission_level ?? 0) >= minLevel;
  }, [user]);

  const canAccess = useCallback((feature: 'agent' | 'data' | 'rag' | 'system' | 'admin') => {
    if (user?.custom_permissions != null) {
      return user.custom_permissions.includes(feature);
    }
    const level = user?.permission_level ?? 0;
    switch (feature) {
      case 'agent': return level >= 2;
      case 'data': return level >= 3;
      case 'rag': return level >= 4;
      case 'system': return level >= 5;
      case 'admin': return level >= 5;
      default: return false;
    }
  }, [user]);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout, refreshUser, hasPermission, canAccess }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
