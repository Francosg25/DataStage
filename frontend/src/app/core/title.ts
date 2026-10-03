import { Injectable, effect, inject, signal } from "@angular/core";
import { Title } from "@angular/platform-browser";
import { RouterStateSnapshot, TitleStrategy } from "@angular/router";
import { I18n } from "./i18n";

@Injectable()
export class LocalizedTitle extends TitleStrategy {
  private title = inject(Title);
  private i18n = inject(I18n);
  private current = signal("DataStage");
  constructor() {
    super();
    effect(() =>
      this.title.setTitle(
        this.current()
          .split(" · ")
          .map((part) => this.i18n.t(part))
          .join(" · "),
      ),
    );
  }
  override updateTitle(snapshot: RouterStateSnapshot) {
    this.current.set(this.buildTitle(snapshot) || "DataStage");
  }
}
