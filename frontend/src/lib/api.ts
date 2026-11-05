"use client";

import { useCallback, useEffect, useState } from "react";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

let csrfToken: string | null = null;
export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

async function parse(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const type = response.headers.get("content-type") ?? "";
  return type.includes("json") ? response.json() : response.blob();
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (method !== "GET" && csrfToken) headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: "same-origin" });
  const body = await parse(response);
  if (!response.ok) {
    const problem = (body ?? {}) as { code?: string; title?: string };
    throw new ApiError(response.status, problem.code ?? "error", problem.title ?? "Request failed");
  }
  return body as T;
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return api<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export interface AsyncState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

export function useApi<T>(path: string | null): AsyncState<T> {
  const [state, setState] = useState<{
    data: T | null;
    error: ApiError | null;
    loading: boolean;
  }>({ data: null, error: null, loading: path !== null });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (path === null) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let active = true;
    setState((previous) => ({ ...previous, loading: true, error: null }));
    api<T>(path)
      .then((data) => active && setState({ data, error: null, loading: false }))
      .catch((error: unknown) => {
        if (!active) return;
        const failure =
          error instanceof ApiError ? error : new ApiError(0, "network", "Network error");
        setState({ data: null, error: failure, loading: false });
      });
    return () => {
      active = false;
    };
  }, [path, tick]);
  const reload = useCallback(() => setTick((value) => value + 1), []);
  return { ...state, reload };
}

/** Downscale photos on the device so uploads work on slow networks. PDFs pass through unchanged. */
export async function compressForUpload(file: File, maxSide = 2000): Promise<File> {
  if (!file.type.startsWith("image/") || typeof createImageBitmap === "undefined") return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const context = canvas.getContext("2d");
    if (!context) return file;
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.85),
    );
    if (!blob || blob.size >= file.size) return file;
    return new File([blob], "prescription.jpg", { type: "image/jpeg" });
  } catch {
    return file;
  }
}
