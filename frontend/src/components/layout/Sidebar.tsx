import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  BookOpen,
  MessageSquare,
  Bot,
  FlaskConical,
  Activity,
  Layers,
  Settings,
} from 'lucide-react';

export type NavTab = 'dashboard' | 'knowledge' | 'chat' | 'agent' | 'evaluation' | 'traces' | 'settings';

export const Sidebar: React.FC = () => {
  const navItems = [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/knowledge', label: 'Knowledge Base', icon: BookOpen },
    { to: '/chat', label: 'RAG Chat', icon: MessageSquare },
    { to: '/agent', label: 'Agent Studio', icon: Bot, badge: 'Tools' },
    { to: '/evaluation', label: 'Evaluation Lab', icon: FlaskConical },
    { to: '/traces', label: 'Observability', icon: Activity },
    { to: '/settings', label: 'Settings', icon: Settings },
  ];

  return (
    <aside className="w-64 border-r border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-950 flex flex-col justify-between p-4 flex-shrink-0 transition-colors">
      <div className="space-y-6">
        <div>
          <div className="text-[11px] font-bold tracking-wider uppercase text-slate-400 dark:text-slate-500 px-3 mb-2">
            Workspace Hub
          </div>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                      isActive
                        ? 'bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-300 border border-indigo-200/80 dark:border-indigo-600/30 font-semibold shadow-sm'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-900/60 border border-transparent'
                    }`
                  }
                >
                  <div className="flex items-center space-x-3">
                    <Icon className="w-4 h-4 flex-shrink-0" />
                    <span>{item.label}</span>
                  </div>
                  {item.badge && (
                    <span className="text-[10px] font-semibold bg-indigo-100 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 px-1.5 py-0.5 rounded border border-indigo-200 dark:border-indigo-800/50">
                      {item.badge}
                    </span>
                  )}
                </NavLink>
              );
            })}
          </nav>
        </div>

        <div className="pt-4 border-t border-slate-200 dark:border-slate-800/80">
          <div className="text-[11px] font-bold tracking-wider uppercase text-slate-400 dark:text-slate-500 px-3 mb-2">
            Active Subsystems
          </div>
          <div className="space-y-2 px-3 text-xs text-slate-600 dark:text-slate-400">
            <div className="flex items-center justify-between">
              <span className="flex items-center space-x-2">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                <span>Hybrid RAG + Rerank</span>
              </span>
              <span className="text-[10px] text-slate-400 dark:text-slate-500">Qdrant</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center space-x-2">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-500"></span>
                <span>Agent Multi-Tool</span>
              </span>
              <span className="text-[10px] text-slate-400 dark:text-slate-500">ReAct</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center space-x-2">
                <span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>
                <span>Deterministic Eval</span>
              </span>
              <span className="text-[10px] text-slate-400 dark:text-slate-500">MRR/nDCG</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center space-x-2">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                <span>Prometheus & Spans</span>
              </span>
              <span className="text-[10px] text-slate-400 dark:text-slate-500">/metrics</span>
            </div>
          </div>
        </div>
      </div>

      <div className="p-3 bg-slate-100/70 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800/80 rounded-2xl text-xs text-slate-600 dark:text-slate-400">
        <div className="flex items-center space-x-2 text-slate-900 dark:text-slate-300 font-semibold mb-1">
          <Layers className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
          <span>IntelligenceOS v1.0</span>
        </div>
        <p className="text-[11px] text-slate-500 leading-relaxed">
          Zero-leakage workspace isolation, verified RAG citations & sandboxed execution.
        </p>
      </div>
    </aside>
  );
};
export default Sidebar;
