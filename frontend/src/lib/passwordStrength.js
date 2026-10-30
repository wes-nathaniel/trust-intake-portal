const COMMON = new Set(["password", "password1", "password123", "12345678", "123456789", "1234567890",
  "qwerty123", "qwertyuiop", "iloveyou", "welcome1", "letmein1", "abc12345", "trustno1"]);

export const MIN_GOOD_SCORE = 3;
export const STRENGTH_LABELS = ["Too short", "Weak", "Fair", "Good", "Strong"];

// Mirrors backend _password_score: 0=too short, 1=weak, 2=fair, 3=good, 4=strong
export function passwordScore(pw = "") {
  if (pw.length < 8) return 0;
  let s = 1;
  if (pw.length >= 12) s += 1;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s += 1;
  if (/\d/.test(pw)) s += 1;
  if (/[^A-Za-z0-9]/.test(pw)) s += 1;
  if (COMMON.has(pw.toLowerCase()) || new Set(pw).size < 4) s = 1;
  return Math.min(s, 4);
}

export function passwordTips(pw = "") {
  const tips = [];
  if (pw.length < 8) tips.push("At least 8 characters");
  if (!(/[a-z]/.test(pw) && /[A-Z]/.test(pw))) tips.push("Upper and lower case letters");
  if (!/\d/.test(pw)) tips.push("A number");
  if (pw.length < 12) tips.push("12+ characters or a symbol makes it stronger");
  return tips;
}
