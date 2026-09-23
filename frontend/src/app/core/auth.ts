import { Injectable, inject, signal } from "@angular/core";
import { CanActivateFn, Router } from "@angular/router";
import { HttpInterceptorFn } from "@angular/common/http";
import { firstValueFrom, from, switchMap } from "rxjs";
import {
  PublicClientApplication,
  InteractionRequiredAuthError,
} from "@azure/msal-browser";
import { Api } from "./api";
import { AppConfig, Identity, errorText } from "./models";
export function isOwnApiUrl(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.origin);
    return (
      parsed.origin === window.location.origin &&
      parsed.pathname.startsWith("/api/")
    );
  } catch {
    return false;
  }
}
@Injectable({ providedIn: "root" })
export class Auth {
  private readonly api = inject(Api);
  private client?: PublicClientApplication;
  readonly config = signal<AppConfig | null>(null);
  readonly user = signal<Identity | null>(null);
  readonly error = signal("");
  readonly ready = signal(false);
  async initialize() {
    try {
      const config = await firstValueFrom(this.api.config());
      this.config.set(config);
      if (config.authMode === "entra") {
        if (
          !config.entra?.tenantId ||
          !config.entra.clientId ||
          !config.entra.apiScope
        )
          throw new Error(
            "La configuración de Microsoft Entra ID está incompleta.",
          );
        this.client = new PublicClientApplication({
          auth: {
            clientId: config.entra.clientId,
            authority: `https://login.microsoftonline.com/${config.entra.tenantId}`,
            redirectUri: window.location.origin + "/login",
          },
          cache: { cacheLocation: "sessionStorage" },
        });
        await this.client.initialize();
        const response = await this.client.handleRedirectPromise();
        const account = response?.account || this.client.getAllAccounts()[0];
        if (account) this.client.setActiveAccount(account);
        if (account) this.user.set(await firstValueFrom(this.api.me()));
      } else if (config.authMode === "development") {
        this.user.set(await firstValueFrom(this.api.me()));
      } else throw new Error("Modo de autenticación no reconocido.");
    } catch (e) {
      this.error.set(
        e instanceof Error && !("status" in e) ? e.message : errorText(e),
      );
    } finally {
      this.ready.set(true);
    }
  }
  async login() {
    if (!this.client || !this.config()?.entra) return;
    await this.client.loginRedirect({
      scopes: [this.config()!.entra!.apiScope],
    });
  }
  async token() {
    if (!this.client) return null;
    const account = this.client.getActiveAccount();
    if (!account) return null;
    try {
      return (
        await this.client.acquireTokenSilent({
          account,
          scopes: [this.config()!.entra!.apiScope],
        })
      ).accessToken;
    } catch (e) {
      if (e instanceof InteractionRequiredAuthError) {
        await this.client.acquireTokenRedirect({
          account,
          scopes: [this.config()!.entra!.apiScope],
        });
        return null;
      }
      throw e;
    }
  }
  async logout() {
    if (this.client)
      await this.client.logoutRedirect({
        postLogoutRedirectUri: window.location.origin + "/login",
      });
  }
  hasRole(...roles: string[]) {
    return !!this.user()?.roles.some((role) =>
      roles.map((r) => r.toLowerCase()).includes(role.toLowerCase()),
    );
  }
}
export const authGuard: CanActivateFn = () =>
  inject(Auth).user() ? true : inject(Router).createUrlTree(["/login"]);
export const operatorGuard: CanActivateFn = () =>
  inject(Auth).hasRole("Operator", "Admin")
    ? true
    : inject(Router).createUrlTree(["/access-denied"]);
export const bearerInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(Auth);
  if (
    !isOwnApiUrl(request.url) ||
    request.url.endsWith("/config") ||
    auth.config()?.authMode !== "entra"
  )
    return next(request);
  return from(auth.token()).pipe(
    switchMap((token) =>
      next(
        token
          ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
          : request,
      ),
    ),
  );
};
