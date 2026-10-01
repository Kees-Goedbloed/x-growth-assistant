import { timingSafeEqual } from "node:crypto";

declare const Netlify: { env: { get(key: string): string | undefined } };

interface EdgeContext {
  next: () => Promise<Response>;
}

const ROBOTS = "noindex, nofollow";
const CACHE = "private, no-store";
const REALM = 'Basic realm="X dashboard", charset="UTF-8"';

export function timingSafeEqualStr(a: string, b: string): boolean {
  const enc = new TextEncoder();
  const ba = enc.encode(a);
  const bb = enc.encode(b);
  const n = Math.max(ba.length, bb.length, 1);
  const pa = new Uint8Array(n);
  const pb = new Uint8Array(n);
  pa.set(ba);
  pb.set(bb);
  const bodyEq = timingSafeEqual(pa, pb);
  const la = new Uint8Array(4);
  const lb = new Uint8Array(4);
  new DataView(la.buffer).setUint32(0, ba.length);
  new DataView(lb.buffer).setUint32(0, bb.length);
  return bodyEq && timingSafeEqual(la, lb);
}

export function parseBasic(header: string | null): { user: string; pass: string } | null {
  if (!header) return null;
  const m = /^Basic\s+(.+)$/i.exec(header.trim());
  if (!m) return null;
  let decoded: string;
  try {
    decoded = atob(m[1]);
  } catch {
    return null;
  }
  const idx = decoded.indexOf(":");
  if (idx < 0) return null;
  return { user: decoded.slice(0, idx), pass: decoded.slice(idx + 1) };
}

export type AuthDecision = { status: 503 } | { status: 401 } | { status: 200 };

/** Only the exact value "public" turns auth off. Missing/empty/garbage → private. */
export function isPublicDashboard(mode: string | undefined | null): boolean {
  return mode === "public";
}

export function decideAuth(
  envUser: string | undefined | null,
  envPass: string | undefined | null,
  header: string | null,
): AuthDecision {
  if (!envUser || !envPass) return { status: 503 };
  const parsed = parseBasic(header);
  if (!parsed) return { status: 401 };
  const userOk = timingSafeEqualStr(parsed.user, envUser);
  const passOk = timingSafeEqualStr(parsed.pass, envPass);
  if (!userOk || !passOk) return { status: 401 };
  return { status: 200 };
}

function applySecurityHeaders(headers: Headers, withAuthChallenge: boolean): void {
  headers.set("X-Robots-Tag", ROBOTS);
  headers.set("Cache-Control", CACHE);
  if (withAuthChallenge) {
    headers.set("WWW-Authenticate", REALM);
  }
}

function deny(status: 401 | 503, body: string): Response {
  const headers = new Headers();
  headers.set("Content-Type", "text/plain; charset=utf-8");
  applySecurityHeaders(headers, status === 401);
  return new Response(body, { status, headers });
}

export default async (request: Request, context: EdgeContext): Promise<Response> => {
  const mode = Netlify.env.get("DASHBOARD_MODE");
  if (isPublicDashboard(mode)) {
    const res = await context.next();
    const headers = new Headers(res.headers);
    headers.set("X-Content-Type-Options", "nosniff");
    headers.set("Referrer-Policy", "no-referrer");
    return new Response(res.body, {
      status: res.status,
      statusText: res.statusText,
      headers,
    });
  }
  const user = Netlify.env.get("DASHBOARD_USER");
  const pass = Netlify.env.get("DASHBOARD_PASSWORD");
  const decision = decideAuth(user, pass, request.headers.get("Authorization"));
  if (decision.status === 503) {
    return deny(503, "Dashboard is not configured.");
  }
  if (decision.status === 401) {
    return deny(401, "Authentication required.");
  }
  const res = await context.next();
  const headers = new Headers(res.headers);
  applySecurityHeaders(headers, false);
  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers,
  });
};
