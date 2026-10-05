import React, { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import { User, Workspace } from '../types';
import { api } from '../api/client';

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';

interface AuthContextType {
  user: User | null;
  workspaces: Workspace[];
  currentWorkspace: Workspace | null;
  setCurrentWorkspace: (workspace: Workspace) => void;
  status: AuthStatus;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, pass: string) => Promise<void>;
  register: (email: string, pass: string, name?: string) => Promise<void>;
  logout: () => void;
  refreshWorkspaces: () => Promise<void>;
  createWorkspace: (name: string) => Promise<Workspace>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const LAST_WORKSPACE_KEY = 'intelligenceos_last_workspace_id';

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentWorkspace, setCurrentWorkspaceState] = useState<Workspace | null>(null);
  const [status, setStatus] = useState<AuthStatus>('loading');

  const setCurrentWorkspace = useCallback((workspace: Workspace) => {
    setCurrentWorkspaceState(workspace);
    try {
      localStorage.setItem(LAST_WORKSPACE_KEY, workspace.id);
    } catch (e) {
      console.warn('Could not persist last workspace ID', e);
    }
  }, []);

  const loadWorkspaces = async (): Promise<Workspace[]> => {
    try {
      const list = await api.listWorkspaces();
      setWorkspaces(list);

      const savedWsId = localStorage.getItem(LAST_WORKSPACE_KEY);
      if (list.length > 0) {
        const matched = list.find((w) => w.id === savedWsId);
        if (matched) {
          setCurrentWorkspaceState(matched);
        } else {
          setCurrentWorkspaceState(list[0]);
          localStorage.setItem(LAST_WORKSPACE_KEY, list[0].id);
        }
      } else {
        setCurrentWorkspaceState(null);
      }
      return list;
    } catch (err) {
      console.error('Failed to load workspaces:', err);
      return [];
    }
  };

  const initAuth = async () => {
    const token = api.getToken();
    if (!token) {
      setStatus('unauthenticated');
      return;
    }

    try {
      const me = await api.getMe();
      setUser(me);
      await loadWorkspaces();
      setStatus('authenticated');
    } catch (err) {
      console.warn('Session restoration failed or expired, resetting credentials:', err);
      api.setToken(null);
      setUser(null);
      setWorkspaces([]);
      setCurrentWorkspaceState(null);
      setStatus('unauthenticated');
    }
  };

  useEffect(() => {
    initAuth();

    const handleUnauthorized = () => {
      setUser(null);
      setWorkspaces([]);
      setCurrentWorkspaceState(null);
      setStatus('unauthenticated');
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
  }, []);

  const login = async (email: string, pass: string) => {
    setStatus('loading');
    try {
      await api.login(email, pass);
      const me = await api.getMe();
      setUser(me);
      await loadWorkspaces();
      setStatus('authenticated');
    } catch (error) {
      setStatus('unauthenticated');
      throw error;
    }
  };

  const register = async (email: string, pass: string, name?: string) => {
    setStatus('loading');
    try {
      await api.register(email, pass, name);
      await api.login(email, pass);
      const me = await api.getMe();
      setUser(me);
      await loadWorkspaces();
      setStatus('authenticated');
    } catch (error) {
      setStatus('unauthenticated');
      throw error;
    }
  };

  const logout = () => {
    api.setToken(null);
    try {
      localStorage.removeItem(LAST_WORKSPACE_KEY);
    } catch {}
    setUser(null);
    setWorkspaces([]);
    setCurrentWorkspaceState(null);
    setStatus('unauthenticated');
  };

  const refreshWorkspaces = async () => {
    await loadWorkspaces();
  };

  const createWorkspace = async (name: string): Promise<Workspace> => {
    const created = await api.createWorkspace(name);
    await refreshWorkspaces();
    setCurrentWorkspace(created);
    return created;
  };

  const isAuthenticated = status === 'authenticated' && !!user;
  const isLoading = status === 'loading';

  return (
    <AuthContext.Provider
      value={{
        user,
        workspaces,
        currentWorkspace,
        setCurrentWorkspace,
        status,
        isAuthenticated,
        isLoading,
        login,
        register,
        logout,
        refreshWorkspaces,
        createWorkspace,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
