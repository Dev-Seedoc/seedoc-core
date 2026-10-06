import "i18next";

import type de from "./de.json";

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation";
    resources: {
      translation: typeof de;
    };
  }
}
