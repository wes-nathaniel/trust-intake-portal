import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Toaster } from "sonner";

import Login from "@/pages/Login";
import Register from "@/pages/Register";
import ClientPortal from "@/pages/ClientPortal";
import StartNew from "@/pages/StartNew";
import IntakeWizard from "@/pages/IntakeWizard";
import AdminDashboard from "@/pages/AdminDashboard";
import AdminCaseDetail from "@/pages/AdminCaseDetail";
import BrandingPage from "@/pages/BrandingPage";
import AcceptInvite from "@/pages/AcceptInvite";
import AdminQuestions from "@/pages/AdminQuestions";
import ProtectedRoute from "@/components/ProtectedRoute";

function Root() {
  const { user } = useAuth();
  if (user === null) return null;
  if (user === false) return <Navigate to="/login" replace />;
  return user.role === "admin" ? <Navigate to="/admin" replace /> : <Navigate to="/portal" replace />;
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <Toaster position="top-right" richColors />
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Root />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/accept-invite" element={<AcceptInvite />} />

            <Route path="/portal" element={<ProtectedRoute><ClientPortal /></ProtectedRoute>} />
            <Route path="/portal/new" element={<ProtectedRoute><StartNew /></ProtectedRoute>} />
            <Route path="/intake/:caseId" element={<ProtectedRoute><IntakeWizard /></ProtectedRoute>} />

            <Route path="/admin" element={<ProtectedRoute adminOnly><AdminDashboard /></ProtectedRoute>} />
            <Route path="/admin/questions" element={<ProtectedRoute adminOnly><AdminQuestions /></ProtectedRoute>} />
            <Route path="/admin/cases/:caseId" element={<ProtectedRoute adminOnly><AdminCaseDetail /></ProtectedRoute>} />
            <Route path="/admin/branding" element={<ProtectedRoute adminOnly><BrandingPage /></ProtectedRoute>} />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
