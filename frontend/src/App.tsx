import { Toaster } from "sonner";
import { Route, Switch } from "wouter";

import ErrorBoundary from "./components/ErrorBoundary";
import { AuthProvider } from "./hooks/useAuth";
import History from "./pages/History";
import Home from "./pages/Home";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import Recommend from "./pages/Recommend";

function Router() {
  return (
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/login" component={Login} />
      <Route path="/recommend" component={Recommend} />
      <Route path="/history" component={History} />
      <Route component={NotFound} />
    </Switch>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <Toaster
          theme="dark"
          toastOptions={{
            style: {
              background: "oklch(0.11 0.008 260)",
              border: "1px solid oklch(0.20 0.01 260)",
              color: "oklch(0.92 0.015 80)",
            },
          }}
        />
        <Router />
      </AuthProvider>
    </ErrorBoundary>
  );
}
