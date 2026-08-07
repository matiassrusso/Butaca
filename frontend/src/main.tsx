import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { installApiLangHeader } from "./lib/apiLang";
import "./index.css";

// antes del primer render: el warm-up de /health de useAuth sale apenas monta
installApiLangHeader();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
