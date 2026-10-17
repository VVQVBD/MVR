import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

/** Сессия вошедшего оператора — отдельно от useSession (демо-сессия менеджера в use-month-close.ts
 *  и use-operator-rating.ts), чтобы вход оператора не подменял токен менеджерской консоли. */
interface OperatorSessionState {
  token: string | null;
  email: string | null;
  setSession: (token: string, email: string) => void;
  clear: () => void;
}

export const useOperatorSession = create<OperatorSessionState>()(
  persist(
    (set) => ({
      token: null,
      email: null,
      setSession: (token, email) => set({ token, email }),
      clear: () => set({ token: null, email: null }),
    }),
    {
      name: "icgroup-operator-session",
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);
