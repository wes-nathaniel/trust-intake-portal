import { useEffect, useRef } from "react";
import api from "@/lib/api";

/**
 * Sends a lightweight heartbeat to POST /api/auth/heartbeat every 60 seconds
 * while the page tab is visible and the user is on the portal.
 * Automatically pauses when the tab is hidden and resumes when it becomes
 * visible again. Stops entirely on unmount (tab closed / navigation away).
 *
 * This is admin-invisible: the backend silently ignores admin users.
 */
export function useHeartbeat(caseId) {
  const intervalRef = useRef(null);
  const caseIdRef = useRef(caseId);
  caseIdRef.current = caseId;

  useEffect(() => {
    const beat = () => {
      api.post("/auth/heartbeat", { case_id: caseIdRef.current || null }).catch(() => {});
    };

    const start = () => {
      if (intervalRef.current) return; // already running
      beat(); // fire immediately on start/resume
      intervalRef.current = setInterval(beat, 60000);
    };

    const stop = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };

    const handleVisibility = () => {
      if (document.visibilityState === "hidden") {
        stop();
      } else {
        start();
      }
    };

    if (document.visibilityState === "visible") {
      start();
    }

    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []); // only mount/unmount — caseId changes are handled via ref
}
