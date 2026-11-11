import axios from "axios";

const BASE = process.env.REACT_APP_BACKEND_URL;
export const API = `${BASE}/api`;

const api = axios.create({
  baseURL: API,
  withCredentials: true,
  timeout: 60000, // 60 s — covers large PDF downloads and slow cold starts
});

// Never timeout file / blob downloads (export.pdf can be large)
api.interceptors.request.use((config) => {
  if (config.responseType === "blob") {
    config.timeout = 0; // unlimited for binary downloads
  }
  return config;
});

export default api;

export function formatApiError(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}
