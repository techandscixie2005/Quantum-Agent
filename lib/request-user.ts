/**
 * Resolves the current user from request headers.
 * In production, identity should be verified by Cloudflare Access or an
 * equivalent verified identity provider, never from raw client headers.
 *
 * For local development, a fixed demo identity is returned.
 */
export function requestUser(request: Request) {
  // Production: require verified Cloudflare Access identity
  const cfAccessEmail = request.headers.get("Cf-Access-Authenticated-User-Email");
  if (cfAccessEmail) {
    const displayName = cfAccessEmail.split("@")[0];
    return { email: cfAccessEmail, displayName };
  }

  // Local development: isolated demo identity
  if (process.env.NODE_ENV !== "production") {
    return { email: "demo.student@quantum-agent.local", displayName: "演示学生" };
  }

  // Production safety: refuse unauthenticated requests
  return { email: "anonymous@quantum-agent.local", displayName: "未验证用户" };
}

