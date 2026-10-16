"use client";

import { Briefcase, Building2, HardHat, UserCog } from "lucide-react";
import type { ComponentType } from "react";

import { Button } from "@/components/ui/button";
import { useMe, useSwitchRole } from "@/hooks/queries";
import type { Role } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ROLE_HINT, ROLE_LABEL, useSession } from "@/store/session";

const ROLES: { role: Role; icon: ComponentType<{ className?: string }> }[] = [
  { role: "executive", icon: Briefcase },
  { role: "manager", icon: UserCog },
  { role: "subcontractor", icon: HardHat },
  { role: "client", icon: Building2 },
];

export function RoleSwitcher() {
  const role = useSession((s) => s.role);
  const switchRole = useSwitchRole();
  const me = useMe();

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Роль для демонстрации доступа">
        {ROLES.map(({ role: r, icon: Icon }) => (
          <Button
            key={r}
            role="radio"
            aria-checked={role === r}
            variant={role === r ? "default" : "outline"}
            size="sm"
            disabled={switchRole.isPending}
            onClick={() => switchRole.mutate(r)}
          >
            <Icon className="h-3.5 w-3.5" />
            {ROLE_LABEL[r]}
          </Button>
        ))}
      </div>
      {switchRole.isError && (
        <p className="text-sm text-destructive">
          Не удалось войти: {switchRole.error.message}. Запустите бекенд с DEMO_MODE=1 и выполните scripts.create_demo_users.
        </p>
      )}
      {role && (
        <p className={cn("text-xs text-muted-foreground", switchRole.isPending && "opacity-50")}>
          {ROLE_HINT[role]}
          {me.data && <span className="ml-1 font-mono">· {me.data.email}</span>}
        </p>
      )}
    </div>
  );
}
