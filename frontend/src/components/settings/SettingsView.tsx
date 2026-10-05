import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import {
  Settings,
  User,
  Shield,
  Building2,
  Moon,
  Sun,
  LogOut,
  CheckCircle2,
  Database,
  Layers,
  KeyRound,
  ExternalLink,
} from 'lucide-react';

export const SettingsView: React.FC = () => {
  const { user, currentWorkspace, workspaces, logout, createWorkspace } = useAuth();
  const { theme, setTheme, toggleTheme } = useTheme();
  const [showNewWsModal, setShowNewWsModal] = useState(false);
  const [newWsName, setNewWsName] = useState('');
  const [isCreatingWs, setIsCreatingWs] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleCreateWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWsName.trim()) return;
    setIsCreatingWs(true);
    try {
      await createWorkspace(newWsName.trim());
      setNewWsName('');
      setShowNewWsModal(false);
      setSuccessMsg(`Workspace created successfully!`);
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: any) {
      alert(`Error creating workspace: ${err.message}`);
    } finally {
      setIsCreatingWs(false);
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-8 animate-fadeIn">
      {/* Header */}
      <div className="pb-6 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-2 text-indigo-600 dark:text-indigo-400 text-xs font-semibold uppercase tracking-wider mb-1">
            <Settings className="w-3.5 h-3.5" />
            <span>Preferences & Management</span>
          </div>
          <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
            System & Account Settings
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
            Manage your account credentials, workspace configurations, security posture, and visual themes.
          </p>
        </div>
      </div>

      {successMsg && (
        <div className="p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-xs text-emerald-700 dark:text-emerald-300 flex items-center space-x-2">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Grid of Settings Cards */}
      <div className="space-y-6">
        {/* Account Profile Card */}
        <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center space-x-3 pb-4 border-b border-slate-100 dark:border-slate-800/80 mb-5">
            <div className="p-2 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
              <User className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-white">Account Profile</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">Authenticated user identity</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <span className="text-slate-500 dark:text-slate-400 font-medium">Email Address</span>
              <div className="mt-1 font-mono text-sm text-slate-900 dark:text-slate-100 bg-slate-50 dark:bg-slate-950 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-800 truncate">
                {user?.email || 'Not authenticated'}
              </div>
            </div>

            <div>
              <span className="text-slate-500 dark:text-slate-400 font-medium">Full Name</span>
              <div className="mt-1 text-sm text-slate-900 dark:text-slate-100 bg-slate-50 dark:bg-slate-950 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-800">
                {user?.full_name || 'Enterprise User'}
              </div>
            </div>

            <div>
              <span className="text-slate-500 dark:text-slate-400 font-medium">User Identifier (UUID)</span>
              <div className="mt-1 font-mono text-xs text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-950 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-800 truncate">
                {user?.id || '—'}
              </div>
            </div>

            <div>
              <span className="text-slate-500 dark:text-slate-400 font-medium">Account Status</span>
              <div className="mt-1 flex items-center space-x-2 text-sm text-emerald-600 dark:text-emerald-400 bg-emerald-50/50 dark:bg-emerald-950/30 px-3.5 py-2 rounded-xl border border-emerald-200 dark:border-emerald-800/40">
                <CheckCircle2 className="w-4 h-4" />
                <span className="font-semibold">Active & Authorized</span>
              </div>
            </div>
          </div>
        </div>

        {/* Visual Appearance / Theme Card */}
        <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center space-x-3 pb-4 border-b border-slate-100 dark:border-slate-800/80 mb-5">
            <div className="p-2 rounded-xl bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400">
              <Sun className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-white">Interface Theme</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">Toggle between dark and light color modes</p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Dark Theme Option */}
            <button
              type="button"
              onClick={() => setTheme('dark')}
              className={`p-4 rounded-2xl border text-left flex items-start space-x-4 transition-all ${
                theme === 'dark'
                  ? 'bg-slate-950 border-indigo-500 shadow-md ring-2 ring-indigo-500/20'
                  : 'bg-slate-950/40 border-slate-200 dark:border-slate-800 hover:border-slate-400 opacity-75 hover:opacity-100'
              }`}
            >
              <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 text-indigo-400">
                <Moon className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-white">Blue / Dark Theme</span>
                  {theme === 'dark' && (
                    <span className="text-[10px] font-semibold bg-indigo-500/20 text-indigo-400 px-2 py-0.5 rounded-full border border-indigo-500/40">
                      Active
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  High-contrast dark slate palette optimized for low-light enterprise analytics.
                </p>
              </div>
            </button>

            {/* Light Theme Option */}
            <button
              type="button"
              onClick={() => setTheme('light')}
              className={`p-4 rounded-2xl border text-left flex items-start space-x-4 transition-all ${
                theme === 'light'
                  ? 'bg-white border-indigo-600 shadow-md ring-2 ring-indigo-600/20'
                  : 'bg-slate-50/60 border-slate-200 dark:border-slate-800 hover:border-slate-400 opacity-75 hover:opacity-100'
              }`}
            >
              <div className="p-2.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-600">
                <Sun className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-slate-900">Blue / White Light Theme</span>
                  {theme === 'light' && (
                    <span className="text-[10px] font-semibold bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-full border border-indigo-200">
                      Active
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Clean crisp high-clarity white background with professional blue accents.
                </p>
              </div>
            </button>
          </div>
        </div>

        {/* Current Workspace Card */}
        <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center space-x-3 pb-4 border-b border-slate-100 dark:border-slate-800/80 mb-5">
            <div className="p-2 rounded-xl bg-cyan-50 dark:bg-cyan-950/60 text-cyan-600 dark:text-cyan-400">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-white">Active Workspace</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">Tenant isolation partition details</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <span className="text-slate-500 dark:text-slate-400 font-medium">Workspace Name</span>
              <div className="mt-1 font-semibold text-sm text-slate-900 dark:text-slate-100 bg-slate-50 dark:bg-slate-950 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-800">
                {currentWorkspace?.name || 'No workspace selected'}
              </div>
            </div>

            <div>
              <span className="text-slate-500 dark:text-slate-400 font-medium">Your Role</span>
              <div className="mt-1 font-semibold text-sm text-slate-900 dark:text-slate-100 bg-slate-50 dark:bg-slate-950 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-800 capitalize">
                {currentWorkspace?.role || 'Owner'}
              </div>
            </div>

            <div>
              <span className="text-slate-500 dark:text-slate-400 font-medium">Workspace UUID</span>
              <div className="mt-1 font-mono text-xs text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-950 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-800 truncate">
                {currentWorkspace?.id || '—'}
              </div>
            </div>

            <div>
              <span className="text-slate-500 dark:text-slate-400 font-medium">Total Workspaces Available</span>
              <div className="mt-1 font-semibold text-sm text-slate-900 dark:text-slate-100 bg-slate-50 dark:bg-slate-950 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-800">
                {workspaces.length} workspace{workspaces.length > 1 ? 's' : ''}
              </div>
            </div>
          </div>
        </div>

        {/* Security and AI Safety Posture */}
        <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center space-x-3 pb-4 border-b border-slate-100 dark:border-slate-800/80 mb-5">
            <div className="p-2 rounded-xl bg-purple-50 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-white">Security & Secret Protection</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">Confidentiality and isolation guarantees</p>
            </div>
          </div>

          <div className="space-y-3 text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
            <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 flex items-start space-x-3">
              <KeyRound className="w-4 h-4 text-indigo-600 dark:text-indigo-400 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-slate-900 dark:text-slate-200">Zero Credential Exposure: </span>
                All API keys (Gemini, Supabase Service Role, Qdrant API Key, Redis secrets) are strictly managed via server environment variables and never shipped to frontend client bundles.
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 flex items-start space-x-3">
              <Shield className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-slate-900 dark:text-slate-200">Multi-Tenant Partitioning: </span>
                All vector searches and object storage requests are bounded by the current workspace UUID. SQL queries in Agent Studio run in read-only sandbox mode with AST mutation prevention.
              </div>
            </div>
          </div>
        </div>

        {/* Session Management */}
        <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">Terminate Session</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Sign out from IntelligenceOS on this browser
            </p>
          </div>

          <button
            type="button"
            onClick={logout}
            className="flex items-center space-x-2 bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/40 dark:hover:bg-rose-900/50 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-900/60 font-semibold px-4 py-2 rounded-xl text-xs transition-colors"
          >
            <LogOut className="w-4 h-4" />
            <span>Sign Out</span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsView;
