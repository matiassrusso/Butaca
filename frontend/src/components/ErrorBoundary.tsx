import { AlertTriangle, RotateCcw } from "lucide-react";
import { Component, ReactNode } from "react";
import { DICTIONARY } from "@/lib/translations";

// ErrorBoundary envuelve a LanguageProvider (ver App.tsx), así que no puede
// usar useLang — y tampoco conviene: es la pantalla que se muestra cuando el
// árbol de React ya se rompió, justo cuando menos hay que depender de un
// context. localStorage es la misma fuente de verdad que usa LanguageProvider.
function copy() {
  try {
    const lang = localStorage.getItem("butaca_lang") === "en" ? "en" : "es";
    return { title: DICTIONARY["errorBoundary.title"][lang], reload: DICTIONARY["errorBoundary.reload"][lang] };
  } catch {
    return { title: DICTIONARY["errorBoundary.title"].es, reload: DICTIONARY["errorBoundary.reload"].es };
  }
}

type Props = {
  children: ReactNode;
};

type State = {
  hasError: boolean;
  error: Error | null;
};

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error) {
    console.error(error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center min-h-screen p-8 bg-background">
          <div className="flex flex-col items-center w-full max-w-2xl p-8">
            <AlertTriangle size={48} className="text-destructive mb-6 shrink-0" />
            <h2 className="text-xl mb-4">{copy().title}</h2>
            <button
              onClick={() => window.location.reload()}
              className="flex items-center gap-2 px-4 py-2 border-2 border-foreground bg-foreground text-background hover:bg-accent hover:border-accent"
            >
              <RotateCcw size={16} />
              {copy().reload}
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
