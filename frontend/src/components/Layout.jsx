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
        <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 flex items-center justify-between h-14 sm:h-16 gap-2">
          <Link to={user && user.role === "admin" ? "/admin" : "/portal"} className="flex items-center gap-2 sm:gap-3 min-w-0" data-testid="brand-link">
            {branding.logo_url ? (
              <img src={branding.logo_url} alt="logo" className="h-8 w-8 sm:h-9 sm:w-9 rounded-sm object-cover shrink-0" />
            ) : (
              <div className="h-8 w-8 sm:h-9 sm:w-9 rounded-sm bg-navy flex items-center justify-center shrink-0">
                <span className="font-serif text-bronze text-lg sm:text-xl font-semibold">T</span>
              </div>
            )}
            <div className="flex flex-col leading-none min-w-0">
              <span className="font-serif text-base sm:text-xl tracking-tight text-navy truncate" data-testid="brand-business-name">
                {branding.business_name}
              </span>
              <span className="hidden sm:inline text-[10px] uppercase tracking-[0.2em] text-[#64748B]">Trust & Estate Portal</span>
            </div>
          </Link>

          {user && user !== false && (
            <nav className="hidden md:flex items-center gap-6 text-sm">
              {user.role === "admin" ? (
                <>
                  <Link to="/admin" className="text-navy hover:text-bronze transition-colors" data-testid="nav-admin-cases">Cases</Link>
                  <Link to="/admin/questions" className="text-navy hover:text-bronze transition-colors" data-testid="nav-admin-questions">Questions</Link>
                  <Link to="/admin/whatsapp-inbox" className="text-navy hover:text-bronze transition-colors" data-testid="nav-admin-whatsapp-inbox">WhatsApp</Link>
                  <Link to="/admin/branding" className="text-navy hover:text-bronze transition-colors" data-testid="nav-admin-branding">Branding</Link>
                </>
              ) : (
                <>
                  <Link to="/portal" className="text-navy hover:text-bronze transition-colors" data-testid="nav-client-portal">My Trust</Link>
                </>
              )}
            </nav>
          )}

          <div className="flex items-center gap-1 sm:gap-3 shrink-0">
            {user && user !== false ? (
              <>
                {user.role === "admin" && <AdminNotifications />}
                <span className="hidden md:inline text-sm text-[#64748B] truncate max-w-[180px]" data-testid="user-email">{user.email}</span>
                <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="logout-btn" className="px-2 sm:px-3">
                  <LogOut className="h-4 w-4 sm:mr-1" /> <span className="hidden sm:inline">Sign out</span>
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

      <main className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 py-6 sm:py-12 fade-in-up">
        {children}
      </main>

      <footer className="border-t border-[#E2E0DA] bg-white mt-16">
        <div className="max-w-7xl mx-auto px-6 py-6 text-xs text-[#64748B] space-y-2">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-2">
            <span>&copy; {new Date().getFullYear()} {branding.business_name}. All rights reserved.</span>
            <span className="font-serif text-sm text-navy" data-testid="footer-prepared-by">
              Prepared by <b>Iron Gate Consulting</b> · Reviewed through military legal benefits
            </span>
            <span>Secure Trust Intake Portal</span>
          </div>
          <p className="text-[10px] text-[#94A3B8] leading-relaxed max-w-4xl mx-auto text-center sm:text-left" data-testid="footer-legal">
            This service is not legal advice. Documents are prepared using standardized trust templates commonly reviewed by military legal professionals.
            Trust laws vary by state and clients may seek independent legal counsel at any time.
          </p>
        </div>
      </footer>
    </div>
  );
}
