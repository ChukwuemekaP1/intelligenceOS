import React from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
  useLocation,
} from 'react-router-dom';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { Navbar } from './components/layout/Navbar';
import { Sidebar } from './components/layout/Sidebar';
import { AuthModal } from './components/auth/AuthModal';
import { NoWorkspaceView } from './components/workspace/NoWorkspaceView';
import { DashboardView } from './components/dashboard/DashboardView';
import { KnowledgeView } from './components/knowledge/KnowledgeView';
import { RAGChatView } from './components/chat/RAGChatView';
import { AgentStudioView } from './components/agent/AgentStudioView';
import { EvaluationView } from './components/evaluation/EvaluationView';
import { TracesView } from './components/traces/TracesView';
import { SettingsView } from './components/settings/SettingsView';
import { Loader2 } from 'lucide-react';

/**
 * Fullscreen Loading / Session Bootstrap Screen
 */
const LoadingScreen: React.FC = () => (
  <div className="h-screen w-screen bg-slate-50 dark:bg-slate-950 flex flex-col items-center justify-center space-y-4 transition-colors">
    <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-600 to-cyan-500 flex items-center justify-center font-bold text-white text-xl shadow-lg shadow-indigo-500/25">
      Ω
    </div>
    <div className="flex items-center space-x-2 text-slate-500 dark:text-slate-400 text-xs font-medium">
      <Loader2 className="w-4 h-4 animate-spin text-indigo-600 dark:text-indigo-400" />
      <span>Bootstrapping IntelligenceOS session...</span>
    </div>
  </div>
);

/**
 * Public Route Guard: If already authenticated, redirect to /dashboard
 */
const PublicRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (isAuthenticated) {
    const from = (location.state as any)?.from?.pathname || '/dashboard';
    return <Navigate to={from} replace />;
  }

  return <>{children}</>;
};

/**
 * Protected Route Guard: If unauthenticated, redirect to /login
 */
const ProtectedRouteLayout: React.FC = () => {
  const { isAuthenticated, isLoading, workspaces, currentWorkspace } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  // If user has zero workspaces, prompt onboarding
  if (workspaces.length === 0 || !currentWorkspace) {
    return (
      <div className="flex flex-col h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 overflow-hidden transition-colors">
        <Navbar />
        <main className="flex-1 overflow-y-auto">
          <NoWorkspaceView />
        </main>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 overflow-hidden transition-colors">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-slate-50/50 dark:bg-slate-950">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      {/* Public Routes */}
      <Route
        path="/login"
        element={
          <PublicRoute>
            <AuthModal initialMode="login" />
          </PublicRoute>
        }
      />
      <Route
        path="/register"
        element={
          <PublicRoute>
            <AuthModal initialMode="register" />
          </PublicRoute>
        }
      />
      <Route
        path="/signup"
        element={
          <PublicRoute>
            <AuthModal initialMode="register" />
          </PublicRoute>
        }
      />

      {/* Protected SaaS Layout */}
      <Route element={<ProtectedRouteLayout />}>
        <Route path="/dashboard" element={<DashboardView />} />
        <Route path="/knowledge" element={<KnowledgeView />} />
        <Route path="/chat" element={<RAGChatView />} />
        <Route path="/agent" element={<AgentStudioView />} />
        <Route path="/evaluation" element={<EvaluationView />} />
        <Route path="/traces" element={<TracesView />} />
        <Route path="/settings" element={<SettingsView />} />
      </Route>

      {/* Default / Fallback Routes */}
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
};

export const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <AuthProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
};

export default App;
