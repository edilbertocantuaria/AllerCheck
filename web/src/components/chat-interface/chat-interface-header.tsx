import { LogIn, LogOut, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ParametersPanel } from "@/components/parameters-panel";
import { ThemeToggle } from "@/components/theme-toggle";
import { type ChatParameters } from "@/lib/chat-types";

interface ChatInterfaceHeaderProps {
  sidebarOpen: boolean;
  isAuthenticated: boolean;
  userEmail?: string;
  parameters: ChatParameters;
  onParametersChange: (params: ChatParameters) => void;
  onLogout: () => void;
  onGoLogin: () => void;
  onGoRegister: () => void;
}

export function ChatInterfaceHeader({
  sidebarOpen,
  isAuthenticated,
  userEmail,
  parameters,
  onParametersChange,
  onLogout,
  onGoLogin,
  onGoRegister
}: ChatInterfaceHeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-border bg-background/80 px-4 py-3 backdrop-blur-sm sticky top-0 z-30">
      <div className="flex items-center gap-2">
        {!sidebarOpen && <div className="w-10" />}
        <h1 className="font-semibold text-foreground">AllerCheck</h1>
      </div>
      <div className="flex items-center gap-1">
        {isAuthenticated && userEmail && (
          <span className="mr-2 hidden text-sm text-muted-foreground sm:inline">
            {userEmail}
          </span>
        )}
        <ParametersPanel
          parameters={parameters}
          onParametersChange={onParametersChange}
        />
        <ThemeToggle />
        {isAuthenticated ? (
          <Button
            variant="ghost"
            size="icon"
            onClick={onLogout}
            className="text-muted-foreground hover:text-foreground"
          >
            <LogOut className="size-5" />
            <span className="sr-only">Sair</span>
          </Button>
        ) : (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={onGoLogin}
              className="hidden sm:inline-flex"
            >
              <LogIn className="size-4" />
              Entrar
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={onGoRegister}
              className="hidden sm:inline-flex"
            >
              <UserPlus className="size-4" />
              Cadastrar
            </Button>
          </>
        )}
      </div>
    </header>
  );
}
