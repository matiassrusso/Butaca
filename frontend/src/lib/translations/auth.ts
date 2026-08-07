import type { Entry } from "./shared";

// Login / registro / invitado / recuperación / verificación de email.
//
// Los mensajes de error que vienen del backend (`detail`) NO se traducen acá:
// llegan ya escritos en español desde la API. Lo de abajo son solo los
// fallbacks del frontend y el chrome de las pantallas.

export const AUTH: Record<string, Entry> = {
  // ─── Login: panel izquierdo ───────────────────────────────────────────
  "auth.heroTitleLead": { es: "Volvé a la", en: "Back to the" },
  "auth.heroTitleAccent": { es: "función", en: "show" },

  // ─── Login: encabezados por modo ──────────────────────────────────────
  "auth.tagClaim": { es: "[Guardá tu cuenta]", en: "[Save your account]" },
  "auth.tagRegister": { es: "[Registro nuevo]", en: "[New sign-up]" },
  "auth.tagRecovery": { es: "[Recuperación]", en: "[Recovery]" },
  "auth.tagLogin": { es: "[Volvés]", en: "[Welcome back]" },
  "auth.claimTitle": { es: "Quedátela", en: "Keep it" },
  "auth.registerTitle": { es: "Creá tu cuenta", en: "Create your account" },
  "auth.forgotTitle": { es: "Recuperá tu clave", en: "Recover your password" },
  "auth.loginTitle": { es: "Entrá", en: "Sign in" },
  "auth.claimSubtitle": {
    es: "Elegí usuario y contraseña. Todo lo que puntuaste como invitado queda igual — es la misma cuenta, ahora con forma de volver a entrar.",
    en: "Pick a username and password. Everything you rated as a guest stays put — same account, now with a way back in.",
  },
  "auth.forgotSubtitle": {
    es: "Ingresá tu usuario y te mandamos un link para elegir una nueva contraseña.",
    en: "Enter your username and we'll send you a link to pick a new password.",
  },
  "auth.loginSubtitle": {
    es: "Necesitamos un usuario para guardar tu historial y tus recomendaciones.",
    en: "We need a username to keep your history and your picks.",
  },

  // ─── Login: formulario ────────────────────────────────────────────────
  "auth.usernameLabel": { es: "Usuario", en: "Username" },
  "auth.emailLabel": { es: "Email", en: "Email" },
  "auth.passwordLabel": { es: "Password", en: "Password" },
  "auth.submitClaim": { es: "Guardar mi cuenta →", en: "Save my account →" },
  "auth.submitRegister": { es: "Crear cuenta →", en: "Create account →" },
  "auth.submitForgot": { es: "Mandar mail →", en: "Send email →" },
  "auth.submitLogin": { es: "Entrar →", en: "Sign in →" },
  "auth.forgotLink": { es: "¿Olvidaste tu contraseña?", en: "Forgot your password?" },
  "auth.toLogin": { es: "¿Ya tenés cuenta? Entrá", en: "Already have an account? Sign in" },
  "auth.toRegister": { es: "¿Primera vez? Registrate", en: "First time? Sign up" },
  "auth.backToLogin": { es: "← Volver a entrar", en: "← Back to sign in" },
  "auth.or": { es: "o", en: "or" },
  "auth.slowHint": {
    es: "Despertando el servidor... la primera vez puede tardar hasta un minuto. Esperá sin recargar.",
    en: "Waking the server up... the first time can take up to a minute. Hang on, don't reload.",
  },

  // ─── Login: Google e invitado ─────────────────────────────────────────
  "auth.googleButton": { es: "Continuar con Google", en: "Continue with Google" },
  "auth.googleKeepsRatings": {
    es: "Con Google también conservás lo que puntuaste.",
    en: "With Google you keep everything you rated too.",
  },
  "auth.guestButton": { es: "Entrar como invitado →", en: "Continue as guest →" },
  "auth.guestDisclaimer": {
    es: "Sin usuario ni mail. Vale para probar, pero si borrás los datos del navegador perdés el acceso.",
    en: "No username, no email. Fine for trying it out, but if you clear your browser data you lose access.",
  },

  // ─── Login: validación y errores ──────────────────────────────────────
  "auth.errUsernameMin": { es: "Mínimo 3 caracteres.", en: "At least 3 characters." },
  "auth.errEmailInvalid": { es: "Ingresá un email válido.", en: "Enter a valid email." },
  "auth.errPasswordMin": { es: "Mínimo 8 caracteres.", en: "At least 8 characters." },
  "auth.errGoogle": { es: "No pude entrar con Google.", en: "Couldn't sign you in with Google." },
  "auth.errGuest": {
    es: "No pude crear una sesión de invitado.",
    en: "Couldn't start a guest session.",
  },
  "auth.errAuth": { es: "Falló la autenticación.", en: "Authentication failed." },

  // ─── Errores que lanza useAuth ────────────────────────────────────────
  // estos son los que EFECTIVAMENTE se ven: la UI muestra err.message, así
  // que los fallbacks de arriba casi nunca llegan a pantalla
  "auth.errLogin": { es: "No pude autenticarte.", en: "Couldn't sign you in." },
  "auth.errClaim": { es: "No pude registrar la cuenta.", en: "Couldn't register the account." },
  "auth.errDelete": { es: "No pude borrar la cuenta.", en: "Couldn't delete the account." },
  "auth.errLetterboxd": {
    es: "No pude guardar tu usuario de Letterboxd.",
    en: "Couldn't save your Letterboxd username.",
  },
  "auth.errSession": { es: "Sesión inválida.", en: "Invalid session." },

  // ─── Recuperación: mail enviado ───────────────────────────────────────
  "auth.forgotSentTitle": { es: "Listo", en: "Done" },
  "auth.forgotSentBody": {
    es: "Si ese usuario existe, le llegó un mail con instrucciones para elegir una nueva contraseña.",
    en: "If that account exists, we sent it an email with instructions to pick a new password.",
  },

  // ─── Reset de contraseña ──────────────────────────────────────────────
  "auth.resetDoneTitle": { es: "Contraseña actualizada", en: "Password updated" },
  "auth.resetTitle": { es: "Elegí una nueva contraseña", en: "Pick a new password" },
  "auth.resetNoToken": {
    es: "Este link no tiene un token válido. Pedí uno nuevo desde el login.",
    en: "This link has no valid token. Request a new one from the sign-in page.",
  },
  "auth.resetGoToLogin": { es: "Ir a entrar →", en: "Go to sign in →" },
  "auth.resetNewPassword": { es: "Nueva password", en: "New password" },
  "auth.resetSubmit": { es: "Cambiar contraseña →", en: "Change password →" },
  "auth.errResetFailed": {
    es: "No pude cambiar tu contraseña.",
    en: "Couldn't change your password.",
  },

  // ─── Verificación de email ────────────────────────────────────────────
  "auth.verifyTag": { es: "[Verificación de email]", en: "[Email verification]" },
  "auth.verifyDoneTitle": { es: "Email confirmado", en: "Email confirmed" },
  "auth.verifyErrorTitle": { es: "No se pudo verificar", en: "Couldn't verify it" },
  "auth.verifyingTitle": { es: "Verificando…", en: "Verifying…" },
  "auth.verifyingBody": { es: "Un segundo…", en: "One second…" },
  "auth.verifyNoToken": {
    es: "Este link no tiene un token válido.",
    en: "This link has no valid token.",
  },
  "auth.verifyErrorHint": {
    es: "Pedí uno nuevo desde el banner en la app.",
    en: "Request a new one from the banner inside the app.",
  },
  "auth.errVerifyFailed": {
    es: "No pude verificar tu email.",
    en: "Couldn't verify your email.",
  },
  "auth.verifyGoHome": { es: "Ir al inicio →", en: "Go home →" },
};
