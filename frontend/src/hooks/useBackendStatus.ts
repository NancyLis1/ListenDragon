import { useEffect, useState } from "react";

import { checkBackend, type BackendStatus } from "../lib/api";

export function useBackendStatus() {
  const [status, setStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    void checkBackend().then(setStatus);
  }, []);

  return status;
}
