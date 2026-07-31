import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001";
const TOKEN_KEY = "butaca_token";

type User = {
  username: string;
  email: string | null;
  emailVerified: boolean;
  // tu cuenta de Letterboxd: la reclama el primer import por username y decide
  // si un import escribe en tu perfil o no (ver /profile/letterboxd)
  letterboxdUsername: string | null;
};

type AuthState = {
  user: User | null;
  token: string | null;
  loading: boolean;
  error: Error | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, email: string) => Promise<void>;
  saveLetterboxdUsername: (letterboxdUsername: string) => Promise<void>;
  logout: () => Promise<void>;
  deleteAccount: (password: string) => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    // warm up the Render free-tier backend on first load so its ~1min cold
    // start overlaps with the user reading the landing / typing credentials,
    // instead of stalling their first real request. Fire-and-forget; a logged-
    // in user's /auth/me below already does this, but a fresh visitor doesn't.
    fetch(`${API_BASE_URL}/health`).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);

    fetch(`${API_BASE_URL}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => {
        if (!response.ok) throw new Error("Sesión inválida.");
        return response.json();
      })
      .then((data) => {
        if (!cancelled)
          setUser({
            username: data.username,
            email: data.email ?? null,
            emailVerified: Boolean(data.email_verified),
            letterboxdUsername: data.letterboxd_username ?? null,
          });
      })
      .catch(() => {
        if (!cancelled) {
          setUser(null);
          setToken(null);
          localStorage.removeItem(TOKEN_KEY);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  const authenticate = useCallback(
    async (endpoint: "login" | "register", username: string, password: string, email?: string) => {
      setError(null);
      const response = await fetch(`${API_BASE_URL}/auth/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(email ? { username, password, email } : { username, password }),
      });

      const body = await response.json().catch(() => null);
      if (!response.ok) {
        const message = body?.detail ?? "No pude autenticarte.";
        const err = new Error(message);
        setError(err);
        throw err;
      }

      localStorage.setItem(TOKEN_KEY, body.token);
      // minimal until the /auth/me effect (fired by setToken) fills in email +
      // verification status
      setUser({
        username: body.username,
        email: null,
        emailVerified: false,
        letterboxdUsername: null,
      });
      setToken(body.token);
    },
    [],
  );

  const login = useCallback(
    (username: string, password: string) => authenticate("login", username, password),
    [authenticate],
  );

  const register = useCallback(
    (username: string, password: string, email: string) =>
      authenticate("register", username, password, email),
    [authenticate],
  );

  const logout = useCallback(async () => {
    if (token) {
      await fetch(`${API_BASE_URL}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => undefined);
    }
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, [token]);

  const deleteAccount = useCallback(
    async (password: string) => {
      if (!token) return;
      const response = await fetch(`${API_BASE_URL}/auth/account`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ password }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "No pude borrar la cuenta.");
      }
      // account (and its session) are gone server-side; clear locally too
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setUser(null);
    },
    [token],
  );

  const saveLetterboxdUsername = useCallback(
    async (letterboxdUsername: string) => {
      if (!token) return;
      const response = await fetch(`${API_BASE_URL}/profile/letterboxd`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ letterboxd_username: letterboxdUsername }),
      });
      if (!response.ok) throw new Error("No pude guardar tu usuario de Letterboxd.");
      const body = await response.json();
      setUser((prev) =>
        prev ? { ...prev, letterboxdUsername: body.letterboxd_username ?? null } : prev,
      );
    },
    [token],
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        loading,
        error,
        isAuthenticated: Boolean(user),
        login,
        register,
        logout,
        deleteAccount,
        saveLetterboxdUsername,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth debe usarse dentro de AuthProvider.");
  }
  return ctx;
}
