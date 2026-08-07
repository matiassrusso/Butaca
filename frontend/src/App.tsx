import { Analytics } from "@vercel/analytics/react";
import { SpeedInsights } from "@vercel/speed-insights/react";
import { Toaster } from "sonner";
import { Route, Switch } from "wouter";

import { AccountBanner } from "./components/AccountBanner";
import ErrorBoundary from "./components/ErrorBoundary";
import { Footer } from "./components/Footer";
import { Navbar } from "./components/Navbar";
import { AuthProvider } from "./hooks/useAuth";
import { LanguageProvider } from "./lib/i18n";
import Games from "./pages/Games";
import History from "./pages/History";
import Home from "./pages/Home";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import PairwiseGame from "./pages/PairwiseGame";
import Profile from "./pages/Profile";
import Rate from "./pages/Rate";
import Recommend from "./pages/Recommend";
import ResetPassword from "./pages/ResetPassword";
import Trivia from "./pages/Trivia";
import VerifyEmail from "./pages/VerifyEmail";

function Router() {
  return (
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/login" component={Login} />
      <Route path="/reset-password" component={ResetPassword} />
      <Route path="/verify-email" component={VerifyEmail} />
      <Route path="/recommend" component={Recommend} />
      <Route path="/rate" component={Rate} />
      <Route path="/games" component={Games} />
      <Route path="/games/pairwise" component={PairwiseGame} />
      <Route path="/games/trivia" component={Trivia} />
      <Route path="/history" component={History} />
      <Route path="/profile" component={Profile} />
      <Route component={NotFound} />
    </Switch>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <LanguageProvider>
      <AuthProvider>
        <Toaster
          toastOptions={{
            style: {
              fontFamily: "var(--font-mono)",
              borderRadius: 0,
            },
          }}
        />
        <div className="min-h-screen flex flex-col bg-background text-foreground">
          <Navbar />
          <AccountBanner />
          <div className="flex-1">
            <Router />
          </div>
          <Footer />
        </div>
        <Analytics />
        <SpeedInsights />
      </AuthProvider>
      </LanguageProvider>
    </ErrorBoundary>
  );
}
