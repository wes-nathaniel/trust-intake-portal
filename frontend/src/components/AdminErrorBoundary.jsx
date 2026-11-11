import React from "react";
import { RefreshCw } from "lucide-react";

export default class AdminErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, errorMessage: error?.message || "Unknown error" };
  }

  componentDidCatch(error, info) {
    // Log to console so it still appears in browser devtools
    console.error("[AdminErrorBoundary] caught:", error, info?.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#FAF8F5] flex items-center justify-center p-6">
          <div className="bg-white border border-[#E2E0DA] rounded-xl shadow-sm p-8 max-w-md w-full text-center">
            <div className="h-12 w-12 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4">
              <span className="text-red-600 text-xl font-bold">!</span>
            </div>
            <h2 className="font-serif text-2xl text-navy mb-2">Something went wrong</h2>
            <p className="text-sm text-[#64748B] mb-1">
              This page hit an unexpected error and could not load.
            </p>
            <p className="text-xs text-[#94A3B8] font-mono mb-6 break-all">
              {this.state.errorMessage}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="inline-flex items-center gap-2 px-6 py-3 bg-navy text-white rounded-lg text-sm font-semibold hover:bg-navy/90 transition-colors min-h-[44px]"
              data-testid="error-boundary-reload-btn"
            >
              <RefreshCw className="h-4 w-4" /> Reload page
            </button>
            <p className="text-xs text-[#94A3B8] mt-4">
              If this keeps happening, contact support.
            </p>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
