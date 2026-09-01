import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type AuthUser } from "./api";

type AuthState = {
  loading: boolean;
  authEnabled: boolean;
  sharedWorkspace: boolean;
  publicBaseUrl: string;
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthState>(null as unknown as AuthState);

export function useAuth() {
  return useContext(Ctx);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [sharedWorkspace, setSharedWorkspace] = useState(true);
  const [publicBaseUrl, setPublicBaseUrl] = useState("");
  const [user, setUser] = useState<AuthUser | null>(null);

  const refresh = async () => {
    const cfg = await api
      .config()
      .catch(() => ({ auth_enabled: false, shared_workspace: true, public_base_url: "" }));
    setAuthEnabled(cfg.auth_enabled);
    setSharedWorkspace(cfg.shared_workspace);
    setPublicBaseUrl(cfg.public_base_url ?? "");
    if (cfg.auth_enabled) setUser(await api.me().catch(() => null));
    else setUser(null);
  };

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    setUser(await api.login(email, password));
  };
  const logout = async () => {
    await api.logout().catch(() => {});
    setUser(null);
  };

  return (
    <Ctx.Provider
      value={{ loading, authEnabled, sharedWorkspace, publicBaseUrl, user, login, logout, refresh }}
    >
      {children}
    </Ctx.Provider>
  );
}
