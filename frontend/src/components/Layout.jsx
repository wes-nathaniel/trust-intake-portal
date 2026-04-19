import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Bell, LogOut, Menu as MenuIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import AdminNotifications from "@/components/AdminNotifications";

export default function Layout({ children }) {
  const { user, branding, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-sand">
      <header className="sticky top-0 z-40 bg-white/90 backdrop-blur-xl border-b border-[#E2E0DA]" data-testid="app-header">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <Link to={user && user.role === "admin" ? "/admin" : "/portal"} className="flex items-center gap-3" data-testid="brand-link">
            {branding.logo_url ? (
              <img src={branding.logo_url} alt="logo" className="h-9 w-9 rounded-sm object-cover" />
            ) : (
              <div className="h-9 w-9 rounded-sm bg-navy flex items-center justify-center">
                <span className="font-serif text-bronze text-xl font-semibold">T</span>
              </div>
            )}
            <div className="flex flex-col leading-none">
              <span className="font-serif text-xl tracking-tight text-navy" data-testid="brand-business-name">
                {branding.business_name}
              </span>
              <span className="text-[10px] uppercase tracking-[0.2em] text-[#64748B]">Trust & Estate Portal</span>
            </div>
          </Link>

          {user && user !== false && (
            <nav className="hidden md:flex items-center gap-6 text-sm">
              {user.role === "admin" ? (
                <>
                  <Link to="/admin" className="text-navy hover:text-bronze transition-colors" data-testid="nav-admin-cases">Cases</Link>
                  <Link to="/admin/branding" className="text-navy hover:text-bronze transition-colors" data-testid="nav-admin-branding">Branding</Link>
                </>
              ) : (
                <>
                  <Link to="/portal" className="text-navy hover:text-bronze transition-colors" data-testid="nav-client-portal">My Trust</Link>
                </>
              )}
            </nav>
          )}

          <div className="flex items-center gap-3">
            {user && user !== false ? (
              <>
                {user.role === "admin" && <AdminNotifications />}
                <span className="hidden sm:inline text-sm text-[#64748B]" data-testid="user-email">{user.email}</span>
                <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn">
                  <LogOut className="h-4 w-4 mr-1" /> Sign out
                </Button>
              </>
            ) : user === false ? (
              <>
                <Link to="/login" className="text-sm text-navy hover:text-bronze" data-testid="nav-login">Sign in</Link>
                <Link to="/register" className="btn-accent text-sm" data-testid="nav-register">Get started</Link>
              </>
            ) : null}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12 fade-in-up">
        {children}
      </main>

      <footer className="border-t border-[#E2E0DA] bg-white mt-16">
        <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-[#64748B]">
          <span>&copy; {new Date().getFullYear()} {branding.business_name}. All rights reserved.</span>
          <span>Secure Trust Intake Portal</span>
        </div>
      </footer>
    </div>
  );
}
