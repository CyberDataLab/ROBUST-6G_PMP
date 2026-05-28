const DEFAULT_ALLOWED_DOMAINS = ["robust-6g.com", "robust-6g.org"];

/** """Validates whether an email belongs to one of the allowed domains, including subdomains.""" */
export function validateEmailDomain(
  email: string,
  allowedDomains: string[] = DEFAULT_ALLOWED_DOMAINS,
): boolean {
  const parts = email.split("@");
  if (parts.length !== 2 || !parts[1]) {
    return false;
  }

  const candidateDomain = parts[1].toLowerCase();

  return allowedDomains.some((domain) => {
    const normalizedDomain = domain.toLowerCase();
    return (
      candidateDomain === normalizedDomain ||
      candidateDomain.endsWith(`.${normalizedDomain}`)
    );
  });
}
