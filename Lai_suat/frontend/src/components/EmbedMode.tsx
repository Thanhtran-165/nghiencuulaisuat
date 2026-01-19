"use client";

import { useEffect } from "react";

export function EmbedMode() {
  useEffect(() => {
    try {
      const isIframe = window.self !== window.top;
      const params = new URLSearchParams(window.location.search);
      const forced = params.get("embed") === "1" || params.get("embed") === "true";

      if (isIframe || forced) {
        document.documentElement.classList.add("embedded");
      } else {
        document.documentElement.classList.remove("embedded");
      }
    } catch {
      // no-op
    }
  }, []);

  return null;
}

