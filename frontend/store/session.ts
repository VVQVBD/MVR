import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { Role } from "@/lib/types";

interface SessionState {
  role: Role | null;
  token: string | null;
  setSession: (role: Role, token: string) => void;
  clear: () => void;
}

/** Текущая демо-роль и её токен. Хранится в sessionStorage вкладки; если он недоступен — только в памяти. */
export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      role: null,
      token: null,
      setSession: (role, token) => set({ role, token }),
      clear: () => set({ role: null, token: null }),
    }),
    {
      name: "icgroup-session",
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);

export const ROLE_LABEL: Record<Role, string> = {
  executive: "Руководитель IC Group",
  manager: "Менеджер IC Line",
  subcontractor: "Субподрядчик",
  client: "Клиент",
  operator: "Оператор",
};

export const ROLE_HINT: Record<Role, string> = {
  executive: "Сквозной доступ: все клиенты, объекты, цены и риски",
  manager: "Сквозной доступ к данным, без управления пользователями",
  subcontractor: "P23 ИП «Шанырак Клин»: только объекты из своего графика, без цен клиента",
  client: "ТОО «Модена Ритейл KZ»: только своя компания и свои спорные вопросы",
  operator: "Личный кабинет: свои заявки, своя премия, выбор района при топ-рейтинге",
};
