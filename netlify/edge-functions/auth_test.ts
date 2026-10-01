import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { decideAuth, isPublicDashboard, parseBasic, timingSafeEqualStr } from "./auth.ts";

Deno.test("timingSafeEqualStr matches identical strings", () => {
  assertEquals(timingSafeEqualStr("secret", "secret"), true);
  assertEquals(timingSafeEqualStr("", ""), true);
});

Deno.test("timingSafeEqualStr rejects mismatches and length differences", () => {
  assertEquals(timingSafeEqualStr("secret", "secreT"), false);
  assertEquals(timingSafeEqualStr("ab", "abc"), false);
  assertEquals(timingSafeEqualStr("abc", "ab"), false);
});

Deno.test("parseBasic splits on the first colon (password may contain colons)", () => {
  const token = btoa("lein:pa:ss:word");
  assertEquals(parseBasic(`Basic ${token}`), { user: "lein", pass: "pa:ss:word" });
  assertEquals(parseBasic(null), null);
  assertEquals(parseBasic("Bearer abc"), null);
  assertEquals(parseBasic("Basic not-base64"), null);
});

Deno.test("decideAuth fails closed without env vars", () => {
  assertEquals(decideAuth(undefined, "x", "Basic " + btoa("a:x")).status, 503);
  assertEquals(decideAuth("a", "", "Basic " + btoa("a:x")).status, 503);
  assertEquals(decideAuth(null, null, null).status, 503);
});

Deno.test("decideAuth returns 401 for missing or wrong credentials", () => {
  const good = "Basic " + btoa("lein:s3cret");
  assertEquals(decideAuth("lein", "s3cret", null).status, 401);
  assertEquals(decideAuth("lein", "s3cret", "Basic " + btoa("lein:wrong")).status, 401);
  assertEquals(decideAuth("lein", "s3cret", "Basic " + btoa("other:s3cret")).status, 401);
  assertEquals(decideAuth("lein", "s3cret", good).status, 200);
});

Deno.test("isPublicDashboard accepts only the exact value public", () => {
  assertEquals(isPublicDashboard("public"), true);
  assertEquals(isPublicDashboard("private"), false);
  assertEquals(isPublicDashboard(undefined), false);
  assertEquals(isPublicDashboard(null), false);
  assertEquals(isPublicDashboard(""), false);
  assertEquals(isPublicDashboard("PUBLIC"), false);
  assertEquals(isPublicDashboard(" garbage "), false);
  assertEquals(isPublicDashboard("public "), false);
});
