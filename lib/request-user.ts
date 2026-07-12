export function requestUser(request: Request) {
  const email = request.headers.get("oai-authenticated-user-email") ?? "demo.student@quantum-agent.local";
  const encodedName = request.headers.get("oai-authenticated-user-full-name");
  let displayName = "演示学生";
  if (encodedName && request.headers.get("oai-authenticated-user-full-name-encoding") === "percent-encoded-utf-8") {
    try { displayName = decodeURIComponent(encodedName); } catch { /* keep fallback */ }
  } else if (!email.endsWith("@quantum-agent.local")) displayName = email.split("@")[0];
  return { email, displayName };
}

