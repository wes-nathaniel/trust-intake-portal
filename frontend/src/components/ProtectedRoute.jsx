import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Loader2 } from "lucide-react";
import ForcePasswordChange from "@/components/ForcePasswordChange";

export default function ProtectedRoute({ children, adminOnly = false }) {
  const { user } = useAuth();
  const location = useLocation();

  if (user === null) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-bronze" />
      </div>
    );
  }
  if (user === false) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  if (user.requires_password_change) {
    return <ForcePasswordChange />;
  }
  if (adminOnly && user.role !== "admin") {
    return <Navigate to="/portal" replace />;
  }
  return children;
}
