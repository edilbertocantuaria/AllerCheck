"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode
} from "react";

interface User {
  id: string;
  email: string;
  created_at: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithGoogle: (idToken: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const TOKEN_KEY = "allercheck_access_token";
const USER_KEY = "allercheck_user";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    try {
      if (typeof window !== "undefined") {
        const storedToken = sessionStorage.getItem(TOKEN_KEY);
        const storedUser = sessionStorage.getItem(USER_KEY);

        if (storedToken && storedUser) {
          setToken(storedToken);
          setUser(JSON.parse(storedUser));
        }
      }
    } catch {
      void 0;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Erro ao fazer login");
    }

    const data = await response.json();
    const accessToken = data.access_token;

    const payload = JSON.parse(atob(accessToken.split(".")[1]));
    const userData: User = {
      id: payload.sub,
      email: payload.email || email,
      created_at: new Date().toISOString()
    };

    setToken(accessToken);
    setUser(userData);

    sessionStorage.setItem(TOKEN_KEY, accessToken);
    sessionStorage.setItem(USER_KEY, JSON.stringify(userData));
  }, []);

  const register = useCallback(
    async (email: string, password: string) => {
      const response = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Erro ao criar conta");
      }

      await login(email, password);
    },
    [login]
  );

  const loginWithGoogle = useCallback(async (idToken: string) => {
    const response = await fetch("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Erro ao autenticar com Google");
    }

    const data = await response.json();
    const accessToken = data.access_token;

    const payload = JSON.parse(atob(accessToken.split(".")[1]));
    const userData: User = {
      id: payload.sub,
      email: payload.email || "",
      created_at: new Date().toISOString()
    };

    setToken(accessToken);
    setUser(userData);

    sessionStorage.setItem(TOKEN_KEY, accessToken);
    sessionStorage.setItem(USER_KEY, JSON.stringify(userData));
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!token,
        login,
        loginWithGoogle,
        register,
        logout
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }

  return context;
}
