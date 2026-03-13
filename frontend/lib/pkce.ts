'use client';

const STORAGE_PREFIX = 'dl_pkce_';

function randomString(length: number): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  let out = '';
  for (let i = 0; i < bytes.length; i += 1) {
    out += chars[bytes[i] % chars.length];
  }
  return out;
}

function toBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

async function sha256(input: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(input);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return toBase64Url(digest);
}

export async function createPkceSession() {
  const state = randomString(32);
  const codeVerifier = randomString(64);
  const codeChallenge = await sha256(codeVerifier);
  sessionStorage.setItem(`${STORAGE_PREFIX}${state}`, codeVerifier);
  return {
    state,
    codeVerifier,
    codeChallenge,
    codeChallengeMethod: 'S256' as const,
  };
}

export function consumePkceVerifier(state: string | null | undefined): string {
  const key = `${STORAGE_PREFIX}${String(state || '').trim()}`;
  const verifier = sessionStorage.getItem(key) || '';
  if (verifier) {
    sessionStorage.removeItem(key);
  }
  return verifier;
}

